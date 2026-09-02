import pytest

from app.models.runtime_thread import RuntimeThread
from app.runtime_threads.models import BoundaryClaimConflict, RuntimeThreadStatus
from app.runtime_threads.sqlalchemy_repository import SqlAlchemyRuntimeThreadRepository

THREAD_ID = "cf:dispatch:TASK-0123456789abcdef0123456789abcde"
TASK_ID = "TASK-0123456789abcdef0123456789abcde"


def add_stable_thread(sqlite_factory) -> None:
    with sqlite_factory() as session:
        session.add(
            RuntimeThread(
                thread_id=THREAD_ID,
                task_id=TASK_ID,
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


def test_override_claim_changes_stable_to_overriding(sqlite_factory) -> None:
    add_stable_thread(sqlite_factory)
    repository = SqlAlchemyRuntimeThreadRepository(sqlite_factory)

    claimed = repository.claim_override_boundary(
        THREAD_ID,
        expected_checkpoint_id="checkpoint-c7",
        expected_state_version=7,
        expected_next_node="capacity",
    )

    assert claimed.status is RuntimeThreadStatus.OVERRIDING
    assert (claimed.current_checkpoint_id, claimed.state_version) == ("checkpoint-c7", 7)


def test_worker_claim_changes_stable_to_running(sqlite_factory) -> None:
    add_stable_thread(sqlite_factory)
    repository = SqlAlchemyRuntimeThreadRepository(sqlite_factory)

    claimed = repository.claim_next_node(
        THREAD_ID,
        expected_checkpoint_id="checkpoint-c7",
        expected_state_version=7,
        expected_next_node="capacity",
        worker_consumer="worker-2",
    )

    assert claimed.status is RuntimeThreadStatus.RUNNING


def test_boundary_claim_has_single_winner(sqlite_factory) -> None:
    add_stable_thread(sqlite_factory)
    override_repository = SqlAlchemyRuntimeThreadRepository(sqlite_factory)
    worker_repository = SqlAlchemyRuntimeThreadRepository(sqlite_factory)

    assert override_repository.claim_override_boundary(
        THREAD_ID,
        expected_checkpoint_id="checkpoint-c7",
        expected_state_version=7,
        expected_next_node="capacity",
    ).status is RuntimeThreadStatus.OVERRIDING

    with pytest.raises(BoundaryClaimConflict):
        worker_repository.claim_next_node(
            THREAD_ID,
            expected_checkpoint_id="checkpoint-c7",
            expected_state_version=7,
            expected_next_node="capacity",
            worker_consumer="worker-2",
        )


def test_worker_winner_prevents_override_claim(sqlite_factory) -> None:
    add_stable_thread(sqlite_factory)
    repository = SqlAlchemyRuntimeThreadRepository(sqlite_factory)
    repository.claim_next_node(
        THREAD_ID,
        expected_checkpoint_id="checkpoint-c7",
        expected_state_version=7,
        expected_next_node="capacity",
        worker_consumer="worker-1",
    )

    with pytest.raises(BoundaryClaimConflict):
        repository.claim_override_boundary(
            THREAD_ID,
            expected_checkpoint_id="checkpoint-c7",
            expected_state_version=7,
            expected_next_node="capacity",
        )
