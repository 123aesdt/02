from app.events.models import TaskEventType
from app.observability.websocket import event_group


def test_websocket_event_groups_are_bounded() -> None:
    assert event_group(TaskEventType.TASK_COMPLETED) == "terminal"
    assert event_group(TaskEventType.GRAPH_MEMORY_COMPLETED) == "memory"
    assert event_group(TaskEventType.RUNTIME_OVERRIDE_APPLIED) == "override"
