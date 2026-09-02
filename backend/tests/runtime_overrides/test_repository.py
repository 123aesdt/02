from dataclasses import replace
from datetime import timedelta

import pytest

from app.models.runtime_override import RuntimeOverrideAttempt
from app.models.runtime_thread import RuntimeThread, RuntimeThreadEvent
from app.runtime_overrides.identity import payload_fingerprint
from app.runtime_overrides.models import RuntimeOverrideIdempotencyConflict
from app.runtime_overrides.sqlalchemy_repository import SqlAlchemyRuntimeOverrideRepository

from .factories import NOW
from .test_models import command


def add_thread(sqlite_factory) -> None:
    with sqlite_factory() as session:
        session.add(
            RuntimeThread(
                thread_id=command().thread_id,
                task_id=command().thread_id.removeprefix("cf:dispatch:"),
                status="STABLE",
                current_checkpoint_id="checkpoint-c7",
                state_version=7,
                current_node="environment",
                next_node="capacity",
                checkpoint_count=4,
                resumed_count=0,
            )
        )
        session.commit()


def test_runtime_override_idempotent_replay(sqlite_factory) -> None:
    add_thread(sqlite_factory)
    repository = SqlAlchemyRuntimeOverrideRepository(sqlite_factory)
    item = command()

    first = repository.begin_or_replay(item, payload_fingerprint(item), intent_expires_at=NOW + timedelta(seconds=10))
    second = repository.begin_or_replay(item, payload_fingerprint(item), intent_expires_at=NOW + timedelta(seconds=10))

    assert (first.override_id, first.replayed) == (item.override_id, False)
    assert (second.override_id, second.replayed) == (item.override_id, True)


def test_runtime_override_idempotency_payload_conflict(sqlite_factory) -> None:
    add_thread(sqlite_factory)
    repository = SqlAlchemyRuntimeOverrideRepository(sqlite_factory)
    item = command()
    repository.begin_or_replay(item, payload_fingerprint(item), intent_expires_at=NOW + timedelta(seconds=10))
    changed = replace(item, new_value="MAINTENANCE")

    with pytest.raises(RuntimeOverrideIdempotencyConflict):
        repository.begin_or_replay(changed, payload_fingerprint(changed), intent_expires_at=NOW + timedelta(seconds=10))


def test_runtime_override_idempotency_actor_conflict(sqlite_factory) -> None:
    add_thread(sqlite_factory)
    repository = SqlAlchemyRuntimeOverrideRepository(sqlite_factory)
    item = command()
    repository.begin_or_replay(item, payload_fingerprint(item), intent_expires_at=NOW + timedelta(seconds=10))

    with pytest.raises(RuntimeOverrideIdempotencyConflict):
        repository.begin_or_replay(
            replace(item, operator_id="operator-2"),
            payload_fingerprint(item),
            intent_expires_at=NOW + timedelta(seconds=10),
        )


def test_runtime_override_attempts_are_append_only(sqlite_factory) -> None:
    add_thread(sqlite_factory)
    repository = SqlAlchemyRuntimeOverrideRepository(sqlite_factory)
    item = command()
    repository.begin_or_replay(item, payload_fingerprint(item), intent_expires_at=NOW + timedelta(seconds=10))

    assert repository.append_attempt(item.override_id, operation="APPLY", status="APPLYING", started_at=NOW) == 1
    assert repository.append_attempt(item.override_id, operation="RECONCILE", status="PARTIAL", started_at=NOW) == 2
    with sqlite_factory() as session:
        assert session.query(RuntimeOverrideAttempt).count() == 2


def test_override_promotion_is_linearization_point(sqlite_factory) -> None:
    add_thread(sqlite_factory)
    runtime_repository = __import__(
        "app.runtime_threads.sqlalchemy_repository", fromlist=["SqlAlchemyRuntimeThreadRepository"]
    ).SqlAlchemyRuntimeThreadRepository(sqlite_factory)
    runtime_repository.claim_override_boundary(
        command().thread_id,
        expected_checkpoint_id="checkpoint-c7",
        expected_state_version=7,
        expected_next_node="capacity",
    )
    repository = SqlAlchemyRuntimeOverrideRepository(sqlite_factory)
    item = command()
    repository.begin_or_replay(item, payload_fingerprint(item), intent_expires_at=NOW + timedelta(seconds=10))
    repository.mark_applying(item.override_id, before_state_version=7, source_checkpoint_id="checkpoint-c7", started_at=NOW)
    repository.attach_result_checkpoint(item.override_id, "checkpoint-c8")

    result = repository.promote_applied(
        item.override_id,
        result_checkpoint_id="checkpoint-c8",
        checkpoint_size_bytes=1200,
        completed_at=NOW,
    )

    with sqlite_factory() as session:
        thread = session.query(RuntimeThread).filter_by(thread_id=item.thread_id).one()
        event = session.query(RuntimeThreadEvent).filter_by(event_key=f"override:{item.override_id}:applied").one()
        assert (thread.current_checkpoint_id, thread.state_version, thread.status) == (
            "checkpoint-c8",
            8,
            "STABLE",
        )
        assert thread.checkpoint_count == 4
        assert (event.checkpoint_id, event.parent_checkpoint_id, event.state_version) == (
            "checkpoint-c8",
            "checkpoint-c7",
            8,
        )
    assert (result.status.value, result.after_state_version) == ("APPLIED", 8)


def test_runtime_override_history_is_newest_first_and_bounded(sqlite_factory) -> None:
    add_thread(sqlite_factory)
    repository = SqlAlchemyRuntimeOverrideRepository(sqlite_factory)
    first = command()
    second = replace(
        first,
        override_id="00000000-0000-0000-0000-000000000009",
        idempotency_key="override-vehicle-9",
        requested_at=NOW + timedelta(seconds=1),
    )
    repository.begin_or_replay(first, payload_fingerprint(first), intent_expires_at=NOW + timedelta(seconds=10))
    repository.begin_or_replay(second, payload_fingerprint(second), intent_expires_at=NOW + timedelta(seconds=11))

    items = repository.list_by_thread(first.thread_id, limit=1)

    assert [item.override_id for item in items] == [second.override_id]
