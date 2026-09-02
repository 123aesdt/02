from datetime import UTC, datetime
from importlib.util import find_spec

import pytest

TASK_ID = "TASK-0123456789abcdef0123456789abcde"


def test_runtime_thread_package_exists():
    assert find_spec("app.runtime_threads") is not None


def test_thread_identity_is_deterministic_and_uses_an_isolated_namespace():
    from app.runtime_threads.identity import thread_id_for_task

    assert thread_id_for_task(TASK_ID) == f"cf:dispatch:{TASK_ID}"
    assert thread_id_for_task(TASK_ID) == thread_id_for_task(TASK_ID)


@pytest.mark.parametrize(
    "task_id",
    ["", "TASK-short", "task-0123456789abcdef0123456789abcde", "TASK-0123456789abcdef0123456789abcd!"],
)
def test_thread_identity_rejects_non_countyflow_task_ids(task_id):
    from app.runtime_threads.identity import thread_id_for_task

    with pytest.raises(ValueError, match="task ID"):
        thread_id_for_task(task_id)


def test_runtime_thread_terminal_is_derived_from_status():
    from app.runtime_threads.models import RuntimeThreadSnapshot, RuntimeThreadStatus

    now = datetime.now(UTC)
    stable = RuntimeThreadSnapshot(
        thread_id=f"cf:dispatch:{TASK_ID}",
        task_id=TASK_ID,
        status=RuntimeThreadStatus.STABLE,
        current_checkpoint_id="checkpoint-1",
        state_version=1,
        current_node="intake",
        next_node="entity_memory",
        checkpoint_count=1,
        checkpoint_size_bytes=512,
        last_event_sequence=None,
        worker_consumer="worker-1",
        resumed_count=0,
        created_at=now,
        updated_at=now,
        terminal_at=None,
        row_version=1,
    )
    terminal = RuntimeThreadSnapshot(
        **{**stable.__dict__, "status": RuntimeThreadStatus.TERMINAL, "next_node": None, "terminal_at": now}
    )

    assert stable.terminal is False
    assert terminal.terminal is True
