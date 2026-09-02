"""Bounded WebSocket event classification."""

from app.events.models import TaskEventType


def event_group(event_type: TaskEventType) -> str:
    value = event_type.value
    if value.startswith("RUNTIME_OVERRIDE"):
        return "override"
    if value.startswith("THREAD_"):
        return "thread"
    if value.startswith("MEMORY_") or value.startswith("GRAPH_MEMORY"):
        return "memory"
    if value in {"TASK_COMPLETED", "TASK_FAILED", "TASK_CANCELLED"}:
        return "terminal"
    if value.startswith(("INTAKE_", "ENVIRONMENT_", "CAPACITY_", "ROUTING_", "DISPATCH_", "AUDIT_")):
        return "agent"
    return "task"
