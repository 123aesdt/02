from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.idempotency.service import IdempotencyService
from app.models.order import Order
from app.runtime_threads.identity import thread_id_for_task

TASK_ID = "TASK-0123456789abcdef0123456789abcde"


def _order(factory) -> int:
    with factory() as session:
        order = Order(
            order_no="ORDER-V2C-REGISTRY",
            status="PENDING",
            driver_id="driver-li",
            vehicle_id="vehicle-cold-a",
            route_id="xinping-road",
            origin="A",
            destination="B",
        )
        session.add(order)
        session.commit()
        return order.id


def _begin(factory):
    from app.runtime_threads.sqlalchemy_repository import SqlAlchemyRuntimeThreadRepository

    IdempotencyService(factory).begin(TASK_ID, _order(factory), "v2c-registry-key")
    return SqlAlchemyRuntimeThreadRepository(factory)


def _promotion(thread_id: str, version: int, old: str | None, new: str, node: str, next_node: str | None):
    from app.runtime_threads.models import PromoteCheckpoint

    return PromoteCheckpoint(
        thread_id=thread_id,
        expected_checkpoint_id=old,
        expected_state_version=version,
        checkpoint_id=new,
        parent_checkpoint_id=old,
        node=node,
        next_node=next_node,
        checkpoint_size_bytes=512 + version,
        worker_consumer="worker-1",
        event_key=f"promoted:{new}",
    )


def test_thread_registry_create(sqlite_factory):
    from app.runtime_threads.models import RuntimeThreadEventType, RuntimeThreadStatus

    repository = _begin(sqlite_factory)

    thread = repository.get_by_task_id(TASK_ID)

    assert thread is not None
    assert thread.thread_id == thread_id_for_task(TASK_ID)
    assert thread.status is RuntimeThreadStatus.RUNNING
    assert thread.current_checkpoint_id is None
    assert thread.state_version == 0
    assert thread.checkpoint_count == 0
    assert thread.terminal is False
    events = repository.list_events(thread.thread_id, 10)
    assert [event.event_type for event in events] == [RuntimeThreadEventType.THREAD_CREATED]


def test_thread_id_stable_across_worker_retry(sqlite_factory):
    from app.models.runtime_thread import RuntimeThread

    repository = _begin(sqlite_factory)
    expected = repository.get_by_task_id(TASK_ID)

    replay = IdempotencyService(sqlite_factory).begin(TASK_ID, expected_task_order(sqlite_factory), "v2c-registry-key")
    actual = repository.get_by_task_id(TASK_ID)

    assert replay.state == "IN_PROGRESS"
    assert actual is not None and expected is not None
    assert actual.thread_id == expected.thread_id
    with sqlite_factory() as session:
        assert session.scalar(select(func.count()).select_from(RuntimeThread)) == 1


def expected_task_order(factory) -> int:
    with factory() as session:
        return session.scalar(select(Order.id).where(Order.order_no == "ORDER-V2C-REGISTRY"))


def test_runtime_thread_unique_constraints_reject_a_second_thread_for_one_task(sqlite_factory):
    from app.models.runtime_thread import RuntimeThread

    repository = _begin(sqlite_factory)
    thread = repository.get_by_task_id(TASK_ID)
    assert thread is not None

    with sqlite_factory() as session:
        session.add(
            RuntimeThread(
                thread_id=f"{thread.thread_id}:duplicate",
                task_id=TASK_ID,
                status="RUNNING",
                state_version=0,
                checkpoint_count=0,
                resumed_count=0,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_checkpoint_history_append_only(sqlite_factory):
    from app.models.runtime_thread import RuntimeThreadEvent
    from app.runtime_threads.models import RuntimeThreadEventType

    repository = _begin(sqlite_factory)
    thread = repository.get_by_task_id(TASK_ID)
    assert thread is not None
    command = _promotion(thread.thread_id, 0, None, "cp-1", "intake", "entity_memory")

    staged = repository.stage_checkpoint(command)
    repository.promote_checkpoint(command)
    history_before = repository.list_events(thread.thread_id, 20)
    repository.promote_checkpoint(_promotion(thread.thread_id, 1, "cp-1", "cp-2", "entity_memory", "graph_memory"))
    history_after = repository.list_events(thread.thread_id, 20)

    assert staged.event_type is RuntimeThreadEventType.CHECKPOINT_STAGED
    assert [(event.event_type, event.checkpoint_id) for event in history_before] == [
        (RuntimeThreadEventType.THREAD_CREATED, None),
        (RuntimeThreadEventType.CHECKPOINT_STAGED, "cp-1"),
        (RuntimeThreadEventType.CHECKPOINT_PROMOTED, "cp-1"),
    ]
    assert history_after[: len(history_before)] == history_before
    with sqlite_factory() as session:
        assert session.scalar(select(func.count()).select_from(RuntimeThreadEvent)) == 4


def test_current_checkpoint_pointer(sqlite_factory):
    repository = _begin(sqlite_factory)
    thread = repository.get_by_task_id(TASK_ID)
    assert thread is not None

    promoted = repository.promote_checkpoint(_promotion(thread.thread_id, 0, None, "cp-1", "intake", "entity_memory"))

    assert promoted.current_checkpoint_id == "cp-1"
    assert promoted.current_node == "intake"
    assert promoted.next_node == "entity_memory"
    assert promoted.checkpoint_size_bytes == 512


def test_state_version_increments(sqlite_factory):
    repository = _begin(sqlite_factory)
    thread = repository.get_by_task_id(TASK_ID)
    assert thread is not None

    versions = []
    old = None
    for version, checkpoint_id, node, next_node in (
        (0, "cp-1", "intake", "entity_memory"),
        (1, "cp-2", "entity_memory", "graph_memory"),
        (2, "cp-3", "graph_memory", "environment"),
    ):
        promoted = repository.promote_checkpoint(
            _promotion(thread.thread_id, version, old, checkpoint_id, node, next_node)
        )
        versions.append(promoted.state_version)
        old = checkpoint_id

    assert versions == [1, 2, 3]
    assert promoted.checkpoint_count == 3


def test_terminal_thread_marked(sqlite_factory):
    from app.runtime_threads.models import RuntimeThreadEventType, RuntimeThreadStatus

    repository = _begin(sqlite_factory)
    thread = repository.get_by_task_id(TASK_ID)
    assert thread is not None
    promoted = repository.promote_checkpoint(_promotion(thread.thread_id, 0, None, "cp-audit", "audit", None))

    terminal = repository.mark_terminal(
        thread.thread_id,
        event_key="terminal:approved",
        worker_consumer="worker-1",
        current_node="audit",
    )
    replay = repository.mark_terminal(
        thread.thread_id,
        event_key="terminal:approved",
        worker_consumer="worker-1",
        current_node="audit",
    )

    assert terminal.status is RuntimeThreadStatus.TERMINAL
    assert terminal.terminal is True
    assert terminal.next_node is None
    assert terminal.current_node == "audit"
    assert terminal.current_checkpoint_id == "cp-audit"
    assert terminal.state_version == promoted.state_version == replay.state_version
    assert terminal.terminal_at is not None and terminal.terminal_at <= datetime.now(UTC)
    events = repository.list_events(thread.thread_id, 20)
    assert [event.event_type for event in events].count(RuntimeThreadEventType.THREAD_TERMINAL) == 1
