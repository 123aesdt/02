import pytest

from app.streams.models import DispatchTaskMessage, StreamMessage
from app.workers.dispatch_worker import DispatchWorker


def _message() -> StreamMessage:
    return StreamMessage(
        "42-0",
        DispatchTaskMessage(
            schema_version="1",
            task_id="TASK-VEHICLE-001",
            order_id=1,
            anomaly_id=10,
            idempotency_key="idem-vehicle-001",
            created_at="2026-09-10T10:42:00+08:00",
            payload={
                "driver_id": "DRIVER-001",
                "vehicle_id": "V-001",
                "route_id": "ROUTE-XP-01",
                "anomaly_type": "VEHICLE_BREAKDOWN",
                "anomaly_description": "发动机冷却系统故障，车辆已安全停驶。",
                "vehicle_status": "BROKEN",
            },
        ),
        None,
        {"stream": "dispatch-tasks"},
    )


class _Queue:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def ensure_consumer_group(self) -> bool:
        self.events.append("group")
        return True

    async def read_group(self, *, count: int, block_ms: int) -> list[StreamMessage]:
        self.events.append("read")
        return [_message()]

    async def ack(self, message_id: str) -> int:
        self.events.append("ack")
        return 1


class _ApprovedGraph:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        self.events.append("graph")
        return {"audit_result": {"audit_status": "APPROVED"}, "requires_manual_review": False}


class _BreakdownHandler:
    def __init__(self, events: list[str], *, fail: bool = False) -> None:
        self.events = events
        self.fail = fail

    def handle_approved_breakdown(self, message: DispatchTaskMessage) -> None:
        self.events.append(f"vehicle_case:{message.task_id}")
        if self.fail:
            raise RuntimeError("maintenance database unavailable")


@pytest.mark.asyncio
async def test_worker_creates_vehicle_rescue_case_before_acknowledging_approved_breakdown():
    queue = _Queue()
    worker = DispatchWorker(
        queue,
        _ApprovedGraph(queue.events),
        read_count=1,
        block_ms=1,
        vehicle_breakdown_handler=_BreakdownHandler(queue.events),
    )

    [result] = await worker.run_once()

    assert result.acknowledged is True
    assert queue.events == ["group", "read", "graph", "vehicle_case:TASK-VEHICLE-001", "ack"]


@pytest.mark.asyncio
async def test_worker_leaves_message_pending_when_vehicle_rescue_case_is_not_durable():
    queue = _Queue()
    worker = DispatchWorker(
        queue,
        _ApprovedGraph(queue.events),
        read_count=1,
        block_ms=1,
        vehicle_breakdown_handler=_BreakdownHandler(queue.events, fail=True),
    )

    [result] = await worker.run_once()

    assert result.acknowledged is False
    assert result.error_code == "VEHICLE_RESCUE_ORCHESTRATION_ERROR"
    assert "ack" not in queue.events
