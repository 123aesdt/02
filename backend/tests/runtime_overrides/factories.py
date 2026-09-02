from datetime import UTC, datetime

from app.runtime_threads.models import RuntimeThreadSnapshot, RuntimeThreadStatus

NOW = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)


def stable_environment_thread(**changes: object) -> RuntimeThreadSnapshot:
    values: dict[str, object] = {
        "thread_id": "cf:dispatch:TASK-0123456789abcdef0123456789abcde",
        "task_id": "TASK-0123456789abcdef0123456789abcde",
        "status": RuntimeThreadStatus.STABLE,
        "current_checkpoint_id": "checkpoint-c7",
        "state_version": 7,
        "current_node": "environment",
        "next_node": "capacity",
        "checkpoint_count": 4,
        "checkpoint_size_bytes": 1024,
        "last_event_sequence": 9,
        "worker_consumer": "worker-1",
        "resumed_count": 0,
        "created_at": NOW,
        "updated_at": NOW,
        "terminal_at": None,
        "row_version": 7,
    }
    values.update(changes)
    return RuntimeThreadSnapshot(**values)


def normal_state(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "task_id": "TASK-0123456789abcdef0123456789abcde",
        "order_id": 1,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-001",
        "vehicle_status": "NORMAL",
        "route_id": "county-101",
        "anomaly_type": "road_risk",
        "anomaly_description": "heavy rain",
        "last_completed_node": "environment",
        "completed_node_count": 4,
    }
    values.update(changes)
    return values
