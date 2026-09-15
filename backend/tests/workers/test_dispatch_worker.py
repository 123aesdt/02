import asyncio
import logging

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
from app.streams.errors import QueueMessageError
from app.streams.models import DispatchTaskMessage, StreamMessage
from app.streams.redis_queue import RedisStreamQueue
from app.workers.dispatch_worker import DispatchWorker, task_message_to_graph_input
from tests.graph.test_routing_agent import _memory_service, _routing_service
from tests.unit.test_dispatch_service import _service


@pytest_asyncio.fixture
async def redis_client():
    client = FakeRedis(decode_responses=False)
    yield client
    await client.aclose()


def _task(
    task_id: str = "task-001",
    *,
    vehicle_status: str = "NORMAL",
    incident_node_id: str | None = None,
    affected_edge_id: str | None = None,
) -> DispatchTaskMessage:
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
            "vehicle_status": vehicle_status,
            "incident_node_id": incident_node_id,
            "affected_edge_id": affected_edge_id,
        },
    )


def test_task_message_to_graph_input_preserves_reported_vehicle_status():
    state = task_message_to_graph_input(_task(vehicle_status="BROKEN"))

    assert state["vehicle_status"] == "BROKEN"


def test_task_message_to_graph_input_preserves_structured_road_location():
    state = task_message_to_graph_input(
        _task(incident_node_id="N04", affected_edge_id="E04")
    )

    assert state["incident_node_id"] == "N04"
    assert state["affected_edge_ids"] == ["E04"]


def _message() -> StreamMessage:
    return StreamMessage("1-0", _task(), None, {"stream": "test"})


class _Queue:
    def __init__(self, messages: list[StreamMessage] | None = None) -> None:
        self.messages = messages or []
        self.events: list[str] = []
        self.acked: list[str] = []
        self.closed = False

    async def ensure_consumer_group(self) -> bool:
        self.events.append("group")
        return True

    async def read_group(self, *, count: int, block_ms: int) -> list[StreamMessage]:
        self.events.append("read")
        return self.messages

    async def ack(self, message_id: str) -> int:
        self.events.append("ack")
        self.acked.append(message_id)
        return 1

    async def close(self) -> None:
        self.closed = True


class _RecoveryQueue(_Queue):
    async def claim_pending(self, *, consumer_name: str, min_idle_ms: int, start_id: str, count: int) -> list[StreamMessage]:
        return self.messages


class _ApprovedGraph:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        self.events.extend(["graph_started", "graph_completed"])
        return {"audit_result": {"audit_status": "APPROVED"}, "requires_manual_review": False}


class _AutomaticPublisher:
    def __init__(self, events: list[str], *, fails: bool = False) -> None:
        self._events = events
        self._fails = fails

    def publish_automatically(self, task_id: str) -> dict[str, object]:
        self._events.append(f"auto_publish:{task_id}")
        if self._fails:
            raise RuntimeError("publication unavailable")
        return {"task_id": task_id, "status": "PUBLISHED"}


@pytest.mark.asyncio
async def test_worker_processes_message_through_graph():
    queue = _Queue([_message()])
    worker = DispatchWorker(queue, _ApprovedGraph(queue.events), read_count=1, block_ms=1)

    [result] = await worker.run_once()

    assert result.task_id == "task-001"
    assert result.terminal_status == "APPROVED"
    assert result.acknowledged is True


@pytest.mark.asyncio
async def test_worker_acks_after_success():
    queue = _Queue([_message()])
    worker = DispatchWorker(queue, _ApprovedGraph(queue.events), read_count=1, block_ms=1)

    await worker.run_once()

    assert queue.events == ["group", "read", "graph_started", "graph_completed", "ack"]


@pytest.mark.asyncio
async def test_worker_auto_publishes_approved_dispatch_before_ack():
    queue = _Queue([_message()])
    worker = DispatchWorker(
        queue,
        _ApprovedGraph(queue.events),
        read_count=1,
        block_ms=1,
        automatic_publication_service=_AutomaticPublisher(queue.events),
    )

    [result] = await worker.run_once()

    assert result.acknowledged is True
    assert queue.events == [
        "group",
        "read",
        "graph_started",
        "graph_completed",
        "auto_publish:task-001",
        "ack",
    ]


@pytest.mark.asyncio
async def test_worker_leaves_approved_message_unacked_when_auto_publish_fails():
    queue = _Queue([_message()])
    worker = DispatchWorker(
        queue,
        _ApprovedGraph(queue.events),
        read_count=1,
        block_ms=1,
        automatic_publication_service=_AutomaticPublisher(queue.events, fails=True),
    )

    [result] = await worker.run_once()

    assert result.acknowledged is False
    assert result.error_code == "AUTO_PUBLICATION_ERROR"
    assert queue.acked == []


@pytest.mark.asyncio
async def test_worker_does_not_auto_publish_manual_review_task():
    class ReviewGraph:
        async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
            return {"audit_result": {"audit_status": "REVIEW_REQUIRED"}, "requires_manual_review": True}

    queue = _Queue([_message()])
    worker = DispatchWorker(
        queue,
        ReviewGraph(),
        read_count=1,
        block_ms=1,
        automatic_publication_service=_AutomaticPublisher(queue.events),
    )

    [result] = await worker.run_once()

    assert result.acknowledged is True
    assert all(not event.startswith("auto_publish:") for event in queue.events)


@pytest.mark.asyncio
async def test_worker_logs_safe_terminal_fields(caplog):
    queue = _Queue([_message()])
    worker = DispatchWorker(
        queue,
        _ApprovedGraph(queue.events),
        read_count=1,
        block_ms=1,
        consumer_name="worker-test-1",
    )

    with caplog.at_level(logging.INFO):
        await worker.run_once()

    assert "task_id=task-001" in caplog.text
    assert "message_id=1-0" in caplog.text
    assert "consumer_name=worker-test-1" in caplog.text
    assert "terminal_status=APPROVED" in caplog.text
    assert "acknowledged=True" in caplog.text
    assert "elapsed_ms=" in caplog.text


@pytest.mark.asyncio
async def test_worker_logs_claimed_pending_message_identity(caplog):
    queue = _RecoveryQueue([StreamMessage("7-0", _task("task-recovered"), 2, {"stream": "test"})])
    worker = DispatchWorker(
        queue,
        _ApprovedGraph(queue.events),
        read_count=1,
        block_ms=1,
        consumer_name="worker-2",
    )

    with caplog.at_level(logging.WARNING):
        await worker.recover_once()

    assert "consumer_name=worker-2" in caplog.text
    assert "message_ids=7-0" in caplog.text
    assert "task_ids=task-recovered" in caplog.text
    assert "recovery_scan_started_epoch_ms=" in caplog.text
    assert "xautoclaim_elapsed_ms=" in caplog.text


@pytest.mark.asyncio
async def test_worker_acks_review_required_terminal_state():
    class ReviewGraph:
        async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
            return {"audit_result": {"audit_status": "REVIEW_REQUIRED"}, "requires_manual_review": True}

    queue = _Queue([_message()])
    [result] = await DispatchWorker(queue, ReviewGraph(), read_count=1, block_ms=1).run_once()

    assert (result.terminal_status, result.acknowledged, result.requires_manual_review) == ("REVIEW_REQUIRED", True, True)


@pytest.mark.asyncio
async def test_worker_does_not_ack_when_graph_fails():
    class FailingGraph:
        async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
            raise RuntimeError("graph failed")

    queue = _Queue([_message()])
    [result] = await DispatchWorker(queue, FailingGraph(), read_count=1, block_ms=1).run_once()

    assert result.acknowledged is False
    assert result.terminal_status == "FAILED"
    assert queue.acked == []


@pytest.mark.asyncio
async def test_worker_does_not_ack_when_audit_not_terminal():
    class AuditFailureGraph:
        async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
            return {
                "audit_result": None,
                "error_code": "AUDIT_PERSISTENCE_ERROR",
                "error_message": "Audit result could not be persisted.",
                "requires_manual_review": True,
            }

    queue = _Queue([_message()])
    [result] = await DispatchWorker(queue, AuditFailureGraph(), read_count=1, block_ms=1).run_once()

    assert (result.acknowledged, result.error_code) == (False, "AUDIT_PERSISTENCE_ERROR")
    assert queue.acked == []


@pytest.mark.asyncio
async def test_worker_handles_invalid_message():
    class InvalidQueue(_Queue):
        async def read_group(self, *, count: int, block_ms: int) -> list[StreamMessage]:
            raise QueueMessageError("invalid stream data")

    queue = InvalidQueue()
    results = await DispatchWorker(queue, _ApprovedGraph(queue.events), read_count=1, block_ms=1).run_once()

    assert results == []
    assert queue.acked == []


@pytest.mark.asyncio
async def test_worker_handles_cancelled_error():
    class CancelledGraph:
        async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
            raise asyncio.CancelledError

    queue = _Queue([_message()])
    worker = DispatchWorker(queue, CancelledGraph(), read_count=1, block_ms=1)

    with pytest.raises(asyncio.CancelledError):
        await worker.run_once()

    assert queue.acked == []


@pytest.mark.asyncio
async def test_worker_graceful_shutdown():
    queue = _Queue()
    worker = DispatchWorker(queue, _ApprovedGraph(queue.events), read_count=1, block_ms=1)

    await worker.shutdown()
    await worker.run_forever()

    assert queue.closed is True
    assert queue.events == []


def test_task_message_to_graph_input():
    graph_input = task_message_to_graph_input(_task())

    assert graph_input == {
        "task_id": "task-001",
        "order_id": 1,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-001",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
        "vehicle_status": "NORMAL",
        "incident_node_id": None,
        "affected_edge_ids": [],
    }


class _RainEnvironmentProvider:
    async def get_environment(self, route_id: str) -> EnvironmentResult:
        return EnvironmentResult("heavy_rain", "slippery", "high", "test_environment", False, None, 1.0)


@pytest.mark.asyncio
async def test_worker_integration_runs_eight_agent_graph_and_acks(redis_client: FakeRedis):
    temp, engine, factory = _service()
    queue = RedisStreamQueue(redis_client, "countyflow:worker:test", "worker-test-group", "worker-test-1")
    try:
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
        await queue.publish(_task())
        [result] = await DispatchWorker(queue, graph, read_count=1, block_ms=1).run_once()
        pending = await redis_client.xpending("countyflow:worker:test", "worker-test-group")
        with factory() as session:
            dispatch = session.scalar(select(Dispatch).where(Dispatch.target_route_id == "national-102"))
            audit = session.scalar(select(AuditRecord).where(AuditRecord.dispatch_id == dispatch.id))

        assert result.acknowledged is True
        assert result.terminal_status == "APPROVED"
        assert pending["pending"] == 0
        assert dispatch.target_route_id == "national-102"
        assert audit.result == "APPROVED"
    finally:
        await queue.close()
        engine.dispose()
        temp.cleanup()
