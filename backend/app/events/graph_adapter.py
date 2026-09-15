from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol

from app.events.broker import TaskEventBroker
from app.events.graph_payloads import (
    project_audit_event,
    project_capacity_event,
    project_dispatch_event,
    project_environment_event,
    project_intake_event,
    project_memory_event,
    project_routing_event,
)
from app.events.models import TaskEvent, TaskEventType
from app.graph.state import DispatchGraphState


class StreamableGraph(Protocol):
    async def astream(self, state: DispatchGraphState, *, stream_mode: str): ...


_NODES = ("intake", "entity_memory", "graph_memory", "environment", "capacity", "routing", "dispatch", "audit")
_EVENT_NAMES = {
    "intake": (TaskEventType.INTAKE_STARTED, TaskEventType.INTAKE_COMPLETED),
    "entity_memory": (TaskEventType.MEMORY_STARTED, TaskEventType.MEMORY_COMPLETED),
    "graph_memory": (TaskEventType.GRAPH_MEMORY_STARTED, TaskEventType.GRAPH_MEMORY_COMPLETED),
    "environment": (TaskEventType.ENVIRONMENT_STARTED, TaskEventType.ENVIRONMENT_COMPLETED),
    "capacity": (TaskEventType.CAPACITY_STARTED, TaskEventType.CAPACITY_COMPLETED),
    "routing": (TaskEventType.ROUTING_STARTED, TaskEventType.ROUTING_COMPLETED),
    "dispatch": (TaskEventType.DISPATCH_STARTED, TaskEventType.DISPATCH_COMPLETED),
    "audit": (TaskEventType.AUDIT_STARTED, TaskEventType.AUDIT_COMPLETED),
}


class GraphEventAdapter:
    def __init__(self, broker: TaskEventBroker) -> None:
        self._broker = broker

    async def invoke(self, graph: StreamableGraph, state: DispatchGraphState) -> Mapping[str, object]:
        task_id = state["task_id"]
        final_state: dict[str, object] = dict(state)
        next_node_index = 0
        await self.publish_started(task_id, _NODES[next_node_index])
        async for update in graph.astream(state, stream_mode="updates"):
            if not isinstance(update, Mapping):
                continue
            for node, patch in update.items():
                if not isinstance(node, str) or not isinstance(patch, Mapping):
                    continue
                final_state.update(patch)
                if node not in _EVENT_NAMES:
                    continue
                await self.publish_completed(task_id, node, patch, final_state)
                next_node_index += 1
                if next_node_index < len(_NODES):
                    next_node = _NODES[next_node_index]
                    await self.publish_started(task_id, next_node)
        return final_state

    async def publish_started(self, task_id: str, node: str) -> None:
        if node not in _EVENT_NAMES:
            return
        await self._publish(task_id, node, _EVENT_NAMES[node][0], "PROCESSING", {})

    async def publish_completed(
        self,
        task_id: str,
        node: str,
        patch: Mapping[str, object],
        state: Mapping[str, object] | None = None,
    ) -> None:
        if node not in _EVENT_NAMES:
            return
        await self._publish(task_id, node, _EVENT_NAMES[node][1], "PROCESSING", self._data_for(node, patch, state))
        if node == "environment" and patch.get("fallback_used") is True:
            await self._publish(
                task_id,
                node,
                TaskEventType.ENVIRONMENT_FALLBACK,
                "PROCESSING",
                {key: patch.get(key) for key in ("fallback_reason", "environment_elapsed_ms", "environment_risk")},
            )
        if node == "graph_memory" and patch.get("graph_memory_error"):
            await self._publish(
                task_id,
                node,
                TaskEventType.GRAPH_MEMORY_DEGRADED,
                "PROCESSING",
                self._data_for(node, patch, state),
            )

    async def _publish(self, task_id: str, node: str, event_type: TaskEventType, status: str, data: Mapping[str, object]) -> None:
        await self._broker.publish(TaskEvent.create(task_id, event_type, node, status, data=self._json_safe(data)))

    @classmethod
    def _data_for(
        cls,
        node: str,
        patch: Mapping[str, object],
        state: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        if node == "intake":
            return project_intake_event(patch)
        if node == "entity_memory":
            return project_memory_event(patch)
        if node == "graph_memory":
            return {
                key: patch.get(key)
                for key in (
                    "graph_memory_used",
                    "graph_memory_error",
                    "graph_memory_elapsed_ms",
                    "graph_memory_facts",
                    "graph_memory_paths",
                )
            }
        if node == "environment":
            return project_environment_event(patch)
        if node == "routing":
            return project_routing_event(patch)
        if node == "capacity":
            return project_capacity_event(state or patch)
        if node == "dispatch":
            return project_dispatch_event(patch.get("dispatch_result"))
        if node == "audit":
            return {"audit_result": project_audit_event(patch.get("audit_result"))}
        return {}

    @classmethod
    def _json_safe(cls, value: object) -> object:
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, Enum):
            return cls._json_safe(value.value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Mapping):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [cls._json_safe(item) for item in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return None
