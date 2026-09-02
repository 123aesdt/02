import re

TASK_ID_PATTERN = re.compile(r"^TASK-[0-9a-f]{31}$")


def thread_id_for_task(task_id: str) -> str:
    if TASK_ID_PATTERN.fullmatch(task_id) is None:
        raise ValueError("Runtime thread task ID is invalid.")
    return f"cf:dispatch:{task_id}"


def thread_id_for_persisted_task(task_id: str) -> str:
    """Map a task already accepted by the persistence boundary to its runtime thread."""
    if not task_id:
        raise ValueError("Runtime thread task ID is invalid.")
    return f"cf:dispatch:{task_id}"
