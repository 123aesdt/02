import asyncio

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from sqlalchemy import select

from app.audit.service import AuditService
from app.capacity.models import CapacitySnapshot
from app.capacity.provider import InMemoryCapacityProvider
from app.capacity.service import CapacityService
from app.dispatch.service import DispatchService
from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.models.audit import AuditRecord
from app.models.dispatch import Dispatch
from app.providers.environment import EnvironmentResult, StaticRouteFallbackProvider
from app.services.circuit_breaker import CircuitBreaker
from app.services.environment import EnvironmentService
from app.streams.models import DispatchTaskMessage
from app.streams.redis_queue import RedisStreamQueue
from app.workers.dispatch_worker import DispatchWorker
from tests.graph.test_routing_agent import _memory_service, _routing_service
from tests.unit.test_dispatch_service import _service

STREAM_NAME = "countyflow:worker:pending"
GROUP_NAME = "countyflow-pending-workers"


@pytest_asyncio.fixture
async def redis_client():
    client = FakeRedis(decode_responses=False)
    yield client
    await client.aclose()


def _task(task_id: str = "task-recovered") -> DispatchTaskMessage:
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


class _ApprovedGraph:
    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        return {"audit_result": {"audit_status": "APPROVED"}, "requires_manual_review": False}


class _FailingGraph:
    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("graph failed")


class _CancelledGraph:
    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        raise asyncio.CancelledError


async def _pending_queue(redis_client: FakeRedis, task: DispatchTaskMessage) -> tuple[RedisStreamQueue, RedisStreamQueue, str]:
    worker_a = RedisStreamQueue(redis_client, STREAM_NAME, GROUP_NAME, "worker-a")
    worker_b = RedisStreamQueue(redis_client, STREAM_NAME, GROUP_NAME, "worker-b")
    await worker_a.ensure_consumer_group()
    message_id = await worker_a.publish(task)
    await worker_a.read_group(count=1, block_ms=1)
    await asyncio.sleep(1.1)
    return worker_a, worker_b, message_id


@pytest.mark.asyncio
async def test_recovered_message_processes_through_worker(redis_client: FakeRedis):
    _, worker_b_queue, message_id = await _pending_queue(redis_client, _task())
    worker = DispatchWorker(worker_b_queue, _ApprovedGraph(), read_count=1, block_ms=1, pending_min_idle_ms=1, recovery_count=10)

    [result] = await worker.recover_once()

    assert result.message_id == message_id
    assert result.task_id == "task-recovered"
    assert result.terminal_status == "APPROVED"


@pytest.mark.asyncio
async def test_recovered_success_is_acked(redis_client: FakeRedis):
    _, worker_b_queue, _ = await _pending_queue(redis_client, _task())
    worker = DispatchWorker(worker_b_queue, _ApprovedGraph(), read_count=1, block_ms=1, pending_min_idle_ms=1, recovery_count=10)

    await worker.recover_once()

    pending = await redis_client.xpending(STREAM_NAME, GROUP_NAME)
    assert pending["pending"] == 0


@pytest.mark.asyncio
async def test_recovered_failure_remains_pending(redis_client: FakeRedis):
    _, worker_b_queue, _ = await _pending_queue(redis_client, _task())
    worker = DispatchWorker(worker_b_queue, _FailingGraph(), read_count=1, block_ms=1, pending_min_idle_ms=1, recovery_count=10)

    [result] = await worker.recover_once()

    pending = await redis_client.xpending(STREAM_NAME, GROUP_NAME)
    assert result.acknowledged is False
    assert result.error_code == "GRAPH_EXECUTION_ERROR"
    assert pending["pending"] == 1


@pytest.mark.asyncio
async def test_recovery_cancelled_error_does_not_ack(redis_client: FakeRedis):
    _, worker_b_queue, _ = await _pending_queue(redis_client, _task())
    worker = DispatchWorker(worker_b_queue, _CancelledGraph(), read_count=1, block_ms=1, pending_min_idle_ms=1, recovery_count=10)

    with pytest.raises(asyncio.CancelledError):
        await worker.recover_once()

    pending = await redis_client.xpending(STREAM_NAME, GROUP_NAME)
    assert pending["pending"] == 1


class _RainEnvironmentProvider:
    async def get_environment(self, route_id: str) -> EnvironmentResult:
        return EnvironmentResult("heavy_rain", "slippery", "high", "test_environment", False, None, 1.0)


@pytest.mark.asyncio
async def test_recovered_message_runs_real_graph_and_persists_terminal_result(redis_client: FakeRedis):
    temp, engine, factory = _service()
    try:
        _, worker_b_queue, message_id = await _pending_queue(redis_client, _task("task-001"))
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
        worker = DispatchWorker(worker_b_queue, graph, read_count=1, block_ms=1, pending_min_idle_ms=1, recovery_count=10)

        [result] = await worker.recover_once()
        pending = await redis_client.xpending(STREAM_NAME, GROUP_NAME)
        with factory() as session:
            dispatch = session.scalar(select(Dispatch).where(Dispatch.target_route_id == "national-102"))
            audit = session.scalar(select(AuditRecord).where(AuditRecord.dispatch_id == dispatch.id))

        assert result.message_id == message_id
        assert result.acknowledged is True
        assert pending["pending"] == 0
        assert dispatch.target_route_id == "national-102"
        assert audit.result == "APPROVED"
    finally:
        engine.dispose()
        temp.cleanup()
