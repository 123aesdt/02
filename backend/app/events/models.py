from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from app.observability.context import current_correlation_id


class TaskEventType(StrEnum):
    TASK_SNAPSHOT = "TASK_SNAPSHOT"
    TASK_ACCEPTED = "TASK_ACCEPTED"
    WORKER_STARTED = "WORKER_STARTED"
    INTAKE_STARTED = "INTAKE_STARTED"
    INTAKE_COMPLETED = "INTAKE_COMPLETED"
    MEMORY_STARTED = "MEMORY_STARTED"
    MEMORY_COMPLETED = "MEMORY_COMPLETED"
    GRAPH_MEMORY_STARTED = "GRAPH_MEMORY_STARTED"
    GRAPH_MEMORY_COMPLETED = "GRAPH_MEMORY_COMPLETED"
    GRAPH_MEMORY_DEGRADED = "GRAPH_MEMORY_DEGRADED"
    ENVIRONMENT_STARTED = "ENVIRONMENT_STARTED"
    ENVIRONMENT_COMPLETED = "ENVIRONMENT_COMPLETED"
    ENVIRONMENT_FALLBACK = "ENVIRONMENT_FALLBACK"
    CAPACITY_STARTED = "CAPACITY_STARTED"
    CAPACITY_COMPLETED = "CAPACITY_COMPLETED"
    ROUTING_STARTED = "ROUTING_STARTED"
    ROUTING_COMPLETED = "ROUTING_COMPLETED"
    DISPATCH_STARTED = "DISPATCH_STARTED"
    DISPATCH_COMPLETED = "DISPATCH_COMPLETED"
    AUDIT_STARTED = "AUDIT_STARTED"
    AUDIT_COMPLETED = "AUDIT_COMPLETED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_REVIEW_REQUIRED = "TASK_REVIEW_REQUIRED"
    TASK_FAILED = "TASK_FAILED"
    MEMORY_MUTATION_REQUESTED = "MEMORY_MUTATION_REQUESTED"
    MEMORY_MUTATION_APPLIED = "MEMORY_MUTATION_APPLIED"
    MEMORY_MUTATION_REJECTED = "MEMORY_MUTATION_REJECTED"
    MEMORY_MUTATION_CONFLICT = "MEMORY_MUTATION_CONFLICT"
    MEMORY_MUTATION_PARTIAL = "MEMORY_MUTATION_PARTIAL"
    THREAD_CHECKPOINTED = "THREAD_CHECKPOINTED"
    THREAD_RESUMED = "THREAD_RESUMED"
    THREAD_TERMINAL = "THREAD_TERMINAL"
    RUNTIME_OVERRIDE_REQUESTED = "RUNTIME_OVERRIDE_REQUESTED"
    RUNTIME_OVERRIDE_APPLIED = "RUNTIME_OVERRIDE_APPLIED"
    RUNTIME_OVERRIDE_REJECTED = "RUNTIME_OVERRIDE_REJECTED"
    RUNTIME_OVERRIDE_CONFLICT = "RUNTIME_OVERRIDE_CONFLICT"
    RUNTIME_OVERRIDE_PARTIAL = "RUNTIME_OVERRIDE_PARTIAL"


@dataclass(frozen=True)
class TaskEvent:
    event_id: str
    task_id: str
    event_type: TaskEventType
    node: str
    status: str
    timestamp: str
    sequence: int = 0
    data: Mapping[str, object] | None = None
    correlation_id: str | None = None

    @classmethod
    def create(
        cls,
        task_id: str,
        event_type: TaskEventType,
        node: str,
        status: str,
        *,
        sequence: int = 0,
        data: Mapping[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> "TaskEvent":
        return cls(
            uuid4().hex,
            task_id,
            event_type,
            node,
            status,
            datetime.now(UTC).isoformat(),
            sequence,
            data or {},
            correlation_id or current_correlation_id(),
        )

    def with_sequence(self, sequence: int) -> "TaskEvent":
        return replace(self, sequence=sequence)

    def with_event_id(self, event_id: str) -> "TaskEvent":
        return replace(self, event_id=event_id)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "TaskEvent":
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise ValueError("Task event data must be an object.")
        values = ("event_id", "task_id", "node", "status", "timestamp")
        if any(not isinstance(payload.get(key), str) for key in values):
            raise ValueError("Task event fields are invalid.")
        sequence = payload.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool):
            raise ValueError("Task event sequence is invalid.")
        return cls(
            str(payload["event_id"]),
            str(payload["task_id"]),
            TaskEventType(str(payload.get("event_type"))),
            str(payload["node"]),
            str(payload["status"]),
            str(payload["timestamp"]),
            sequence,
            dict(data),
            str(payload["correlation_id"]) if payload.get("correlation_id") else None,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "task_id": self.task_id,
            "event_type": self.event_type.value,
            "node": self.node,
            "status": self.status,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
            "data": dict(self.data or {}),
            "correlation_id": self.correlation_id,
        }
