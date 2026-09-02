import asyncio

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from redis.exceptions import ConnectionError
from sqlalchemy import select

from app.audit.service import AuditService
from app.capacity.models import CapacitySnapshot
from app.capacity.provider import InMemoryCapacityProvider
from app.capacity.service import CapacityService
from app.dispatch.service import DispatchService
from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.idempotency.service import IdempotencyService
from app.models.audit import AuditRecord
from app.models.dispatch import Dispatch
from app.models.task import DispatchTask
from app.providers.environment import EnvironmentResult, StaticRouteFallbackProvider
from app.services.circuit_breaker import CircuitBreaker
from app.services.environment import EnvironmentService
from app.streams.errors import QueueConnectionError
from app.streams.models import DeadLetterMessage, DispatchTaskMessage, StreamMessage
from app.streams.redis_queue import RedisStreamQueue
from app.streams.retry import RetryPolicy
from app.workers.dispatch_worker import DispatchWorker
from tests.graph.test_routing_agent import _memory_service, _routing_service
from tests.unit.test_dispatch_service import _service

STREAM_NAME = "countyflow:worker:retry"
DLQ_STREAM_NAME = "countyflow:worker:retry:dlq"
GROUP_NAME = "countyflow-retry-workers"


@pytest_asyncio.fixture
async def redis_client():
    client = FakeRedis(decode_responses=False)
    yield client
    await client.aclose()


def _task(task_id: str = "task-retry-worker") -> DispatchTaskMessage:
    return DispatchTaskMessage(
        schema_version="1",
        task_id=task_id,
        order_id=1,
        anomaly_id=10,
        idempotency_key=f"idem-{task_id}",
        created_at="2026-08-21T00:00:00+00:00",
        payload={
            "driver_id": "driver-li",
            "vehicle_id": "vehicle-001",
            "route_id": "xinping-road",
            "anomaly_type": "rain_slippery",
            "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
        },
    )


def _queue(redis_client: FakeRedis, consumer_name: str) -> RedisStreamQueue:
    return RedisStreamQueue(redis_client, STREAM_NAME, GROUP_NAME, consumer_name, dlq_stream_name=DLQ_STREAM_NAME)


def _policy() -> RetryPolicy:
    return RetryPolicy(max_delivery_attempts=3, base_delay_ms=1000, max_delay_ms=30_000)


class _ApprovedGraph:
    def __init__(self) -> None:
        self.invocations = 0

    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        self.invocations += 1
        return {"audit_result": {"audit_status": "APPROVED"}, "requires_manual_review": False}


class _FailingGraph:
    def __init__(self) -> None:
        self.invocations = 0

    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        self.invocations += 1
        raise RuntimeError("graph failed")


async def _pending_for_recovery(redis_client: FakeRedis, task: DispatchTaskMessage | None = None) -> tuple[RedisStreamQueue, RedisStreamQueue, str]:
    worker_a = _queue(redis_client, "worker-a")
    worker_b = _queue(redis_client, "worker-b")
    await worker_a.ensure_consumer_group()
    message_id = await worker_a.publish(task or _task())
    await worker_a.read_group(count=1, block_ms=1)
    await asyncio.sleep(1.1)
    return worker_a, worker_b, message_id


@pytest.mark.asyncio
async def test_recovery_retries_before_delivery_limit(redis_client: FakeRedis):
    _, queue, _ = await _pending_for_recovery(redis_client)
    graph = _FailingGraph()

    async def fake_sleep(seconds: float) -> None:
        return None

    [result] = await DispatchWorker(
        queue, graph, read_count=1, block_ms=1, pending_min_idle_ms=1, recovery_count=1, retry_policy=_policy(), sleep_func=fake_sleep
    ).recover_once()

    assert (result.delivery_count, result.retried, result.moved_to_dlq, graph.invocations) == (2, True, False, 1)


@pytest.mark.asyncio
async def test_recovery_applies_backoff_before_retry(redis_client: FakeRedis):
    _, queue, _ = await _pending_for_recovery(redis_client)
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    await DispatchWorker(
        queue, _FailingGraph(), read_count=1, block_ms=1, pending_min_idle_ms=1, recovery_count=1, retry_policy=_policy(), sleep_func=fake_sleep
    ).recover_once()

    assert delays == [2.0]


@pytest.mark.asyncio
async def test_recovery_moves_message_to_dlq_at_limit(redis_client: FakeRedis):
    _, queue, original_id = await _pending_for_recovery(redis_client)
    graph = _FailingGraph()

    async def fake_sleep(seconds: float) -> None:
        return None

    worker = DispatchWorker(queue, graph, read_count=1, block_ms=1, pending_min_idle_ms=1, recovery_count=1, retry_policy=_policy(), sleep_func=fake_sleep)
    await worker.recover_once()
    await asyncio.sleep(1.1)
    [result] = await worker.recover_once()
    [(dlq_id, fields)] = await redis_client.xrange(DLQ_STREAM_NAME)
    dlq_message = DeadLetterMessage.from_json(fields[b"data"])

    assert dlq_id
    assert result.moved_to_dlq is True
    assert dlq_message.original_message_id == original_id


@pytest.mark.asyncio
async def test_recovery_does_not_execute_graph_after_retry_limit(redis_client: FakeRedis):
    _, queue, _ = await _pending_for_recovery(redis_client)
    graph = _FailingGraph()

    async def fake_sleep(seconds: float) -> None:
        return None

    worker = DispatchWorker(queue, graph, read_count=1, block_ms=1, pending_min_idle_ms=1, recovery_count=1, retry_policy=_policy(), sleep_func=fake_sleep)
    await worker.recover_once()
    await asyncio.sleep(1.1)
    await worker.recover_once()

    assert graph.invocations == 1


@pytest.mark.asyncio
async def test_dlq_success_removes_message_from_pending(redis_client: FakeRedis):
    _, queue, _ = await _pending_for_recovery(redis_client)

    async def fake_sleep(seconds: float) -> None:
        return None

    worker = DispatchWorker(
        queue, _FailingGraph(), read_count=1, block_ms=1, pending_min_idle_ms=1, recovery_count=1, retry_policy=_policy(), sleep_func=fake_sleep
    )
    await worker.recover_once()
    await asyncio.sleep(1.1)
    await worker.recover_once()

    assert (await redis_client.xpending(STREAM_NAME, GROUP_NAME))["pending"] == 0


@pytest.mark.asyncio
async def test_dlq_failure_keeps_message_pending(redis_client: FakeRedis, monkeypatch):
    _, queue, _ = await _pending_for_recovery(redis_client)

    async def fake_sleep(seconds: float) -> None:
        return None

    worker = DispatchWorker(
        queue, _FailingGraph(), read_count=1, block_ms=1, pending_min_idle_ms=1, recovery_count=1, retry_policy=_policy(), sleep_func=fake_sleep
    )
    await worker.recover_once()
    await asyncio.sleep(1.1)

    async def failed_xadd(*args, **kwargs):
        raise ConnectionError("dlq offline")

    monkeypatch.setattr(redis_client, "xadd", failed_xadd)

    with pytest.raises(QueueConnectionError):
        await worker.recover_once()

    assert (await redis_client.xpending(STREAM_NAME, GROUP_NAME))["pending"] == 1


@pytest.mark.asyncio
async def test_cancelled_during_backoff_does_not_ack(redis_client: FakeRedis):
    _, queue, _ = await _pending_for_recovery(redis_client)

    async def cancelled_sleep(seconds: float) -> None:
        raise asyncio.CancelledError

    worker = DispatchWorker(
        queue, _ApprovedGraph(), read_count=1, block_ms=1, pending_min_idle_ms=1, recovery_count=1, retry_policy=_policy(), sleep_func=cancelled_sleep
    )

    with pytest.raises(asyncio.CancelledError):
        await worker.recover_once()

    assert (await redis_client.xpending(STREAM_NAME, GROUP_NAME))["pending"] == 1


@pytest.mark.asyncio
async def test_failed_retry_remains_pending(redis_client: FakeRedis):
    _, queue, _ = await _pending_for_recovery(redis_client)

    async def fake_sleep(seconds: float) -> None:
        return None

    [result] = await DispatchWorker(
        queue, _FailingGraph(), read_count=1, block_ms=1, pending_min_idle_ms=1, recovery_count=1, retry_policy=_policy(), sleep_func=fake_sleep
    ).recover_once()

    assert result.acknowledged is False
    assert (await redis_client.xpending(STREAM_NAME, GROUP_NAME))["pending"] == 1


@pytest.mark.asyncio
async def test_retry_to_dlq_preserves_original_identity(redis_client: FakeRedis):
    worker_a_queue = _queue(redis_client, "worker-a")
    worker_b_queue = _queue(redis_client, "worker-b")
    first_graph = _FailingGraph()
    retry_graph = _FailingGraph()

    async def fake_sleep(seconds: float) -> None:
        return None

    await worker_a_queue.ensure_consumer_group()
    original_id = await worker_a_queue.publish(_task())
    await DispatchWorker(
        worker_a_queue,
        first_graph,
        read_count=1,
        block_ms=1,
        retry_policy=_policy(),
        sleep_func=fake_sleep,
    ).run_once()
    assert (first_graph.invocations, (await redis_client.xpending(STREAM_NAME, GROUP_NAME))["pending"]) == (1, 1)

    await asyncio.sleep(1.1)
    retry_worker = DispatchWorker(
        worker_b_queue,
        retry_graph,
        read_count=1,
        block_ms=1,
        pending_min_idle_ms=1,
        recovery_count=1,
        retry_policy=_policy(),
        sleep_func=fake_sleep,
    )
    [retry_result] = await retry_worker.recover_once()
    assert (retry_result.delivery_count, retry_result.retried, retry_graph.invocations) == (2, True, 1)
    assert (await redis_client.xpending(STREAM_NAME, GROUP_NAME))["pending"] == 1

    await asyncio.sleep(1.1)
    [dlq_result] = await retry_worker.recover_once()
    [(dlq_id, fields)] = await redis_client.xrange(DLQ_STREAM_NAME)
    dlq_message = DeadLetterMessage.from_json(fields[b"data"])

    assert dlq_id
    assert dlq_result.moved_to_dlq is True
    assert retry_graph.invocations == 1
    assert (await redis_client.xpending(STREAM_NAME, GROUP_NAME))["pending"] == 0
    assert (dlq_message.original_message_id, dlq_message.task_id, dlq_message.idempotency_key) == (
        original_id,
        "task-retry-worker",
        "idem-task-retry-worker",
    )


@pytest.mark.asyncio
async def test_dlq_persists_canonical_task_terminal_before_message_removal(redis_client: FakeRedis):
    temp, engine, factory = _service()
    try:
        ledger = IdempotencyService(factory)
        ledger.mark_processing("task-001")
        worker = DispatchWorker(
            _queue(redis_client, "worker-dlq"),
            _FailingGraph(),
            read_count=1,
            block_ms=1,
            retry_policy=_policy(),
            idempotency_service=ledger,
        )

        result = await worker._recover_message(
            StreamMessage("3-0", _task("task-001"), 3, {"stream": STREAM_NAME})
        )
        with factory() as session:
            task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == "task-001"))

        assert result.moved_to_dlq is True
        assert task.status == "DLQ"
        assert task.completed_at is not None
    finally:
        engine.dispose()
        temp.cleanup()


class _RainEnvironmentProvider:
    async def get_environment(self, route_id: str) -> EnvironmentResult:
        return EnvironmentResult("heavy_rain", "slippery", "high", "test_environment", False, None, 1.0)


@pytest.mark.asyncio
async def test_retry_success_is_acked(redis_client: FakeRedis):
    temp, engine, factory = _service()
    try:
        _, queue, _ = await _pending_for_recovery(redis_client, _task("task-001"))
        graph = build_graph(
            GraphDependencies(
                entity_memory_service=await _memory_service(),
                environment_service=EnvironmentService(_RainEnvironmentProvider(), StaticRouteFallbackProvider(), CircuitBreaker(3, 5.0)),
                capacity_service=CapacityService(
                    InMemoryCapacityProvider({("driver-li", "vehicle-001"): CapacitySnapshot(True, True, 0.45, 0.60, "in_memory_capacity")}),
                    limited_threshold=0.8,
                    unavailable_threshold=1.0,
                ),
                routing_service=_routing_service(),
                dispatch_service=DispatchService(factory),
                audit_service=AuditService(factory),
            )
        )
        delays: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            delays.append(seconds)

        [result] = await DispatchWorker(
            queue, graph, read_count=1, block_ms=1, pending_min_idle_ms=1, recovery_count=1, retry_policy=_policy(), sleep_func=fake_sleep
        ).recover_once()
        with factory() as session:
            dispatch = session.scalar(select(Dispatch).where(Dispatch.target_route_id == "national-102"))
            audit = session.scalar(select(AuditRecord).where(AuditRecord.dispatch_id == dispatch.id))

        assert (result.acknowledged, result.retried, delays) == (True, True, [2.0])
        assert (await redis_client.xpending(STREAM_NAME, GROUP_NAME))["pending"] == 0
        assert await redis_client.xrange(DLQ_STREAM_NAME) == []
        assert dispatch.target_route_id == "national-102"
        assert audit.result == "APPROVED"
    finally:
        engine.dispose()
        temp.cleanup()
