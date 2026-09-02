from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.events.broker import InMemoryTaskEventBroker
from app.events.models import TaskEvent, TaskEventType
from app.runtime_threads.events import RuntimeThreadEventPublisher
from app.runtime_threads.models import RuntimeThreadSnapshot, RuntimeThreadStatus


def _thread():
    now = datetime.now(UTC)
    return RuntimeThreadSnapshot(
        thread_id="cf:dispatch:TASK-5123456789abcdef0123456789abcde",
        task_id="TASK-5123456789abcdef0123456789abcde",
        status=RuntimeThreadStatus.STABLE,
        current_checkpoint_id="checkpoint-1",
        state_version=1,
        current_node="routing",
        next_node="dispatch",
        checkpoint_count=1,
        checkpoint_size_bytes=845,
        last_event_sequence=None,
        worker_consumer="worker-1",
        resumed_count=0,
        created_at=now,
        updated_at=now,
        terminal_at=None,
        row_version=1,
    )


class _Repository:
    def __init__(self, thread):
        self.thread = thread
        self.sequences = []

    def update_last_event_sequence(self, thread_id, sequence):
        assert thread_id == self.thread.thread_id
        self.sequences.append(sequence)
        self.thread = replace(self.thread, last_event_sequence=sequence)
        return self.thread


@pytest.mark.asyncio
async def test_checkpoint_event():
    broker = InMemoryTaskEventBroker()
    repository = _Repository(_thread())
    publisher = RuntimeThreadEventPublisher(broker, repository)
    await broker.publish(
        TaskEvent.create(
            _thread().task_id,
            TaskEventType.ROUTING_COMPLETED,
            "routing",
            "PROCESSING",
            data={"decision": "REROUTE"},
        )
    )

    published = await publisher.publish_checkpoint(_thread())

    assert published.event_type is TaskEventType.THREAD_CHECKPOINTED
    assert published.sequence == 2
    assert published.data == {
        "thread_id": _thread().thread_id,
        "checkpoint_id": "checkpoint-1",
        "state_version": 1,
        "node": "routing",
        "next_node": "dispatch",
        "checkpoint_size_bytes": 845,
    }
    forbidden_keys = {"state", "anomaly_description", "memory_evidence", "authorization", "redis_url", "exception"}
    assert forbidden_keys.isdisjoint(published.data or {})
    assert repository.sequences == [2]


@pytest.mark.asyncio
async def test_resume_event_includes_resume_count():
    broker = InMemoryTaskEventBroker()
    resumed = replace(_thread(), resumed_count=2)
    publisher = RuntimeThreadEventPublisher(broker, _Repository(resumed))

    published = await publisher.publish_resumed(resumed)

    assert published.data["resume_count"] == 2


@pytest.mark.asyncio
async def test_capacity_event_projects_canonical_checkpoint_state():
    broker = InMemoryTaskEventBroker()
    publisher = RuntimeThreadEventPublisher(broker, _Repository(_thread()))

    await publisher(
        _thread(),
        "capacity",
        {"capacity_state": {"vehicle_available": False, "capacity_status": "UNAVAILABLE", "risk_level": "high", "reason": "Vehicle runtime status is BROKEN."}},
        {"vehicle_id": "vehicle-001", "vehicle_status": "BROKEN"},
    )

    capacity = next(event for event in await broker.history(_thread().task_id) if event.event_type is TaskEventType.CAPACITY_COMPLETED)
    assert capacity.data["vehicle_id"] == "vehicle-001"
    assert capacity.data["vehicle_status"] == "BROKEN"
