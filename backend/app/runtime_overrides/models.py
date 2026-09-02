from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.runtime_threads.models import CheckpointRecord


class VehicleRuntimeStatus(StrEnum):
    NORMAL = "NORMAL"
    BROKEN = "BROKEN"
    UNAVAILABLE = "UNAVAILABLE"
    MAINTENANCE = "MAINTENANCE"


class RuntimeOverrideStatus(StrEnum):
    PENDING = "PENDING"
    APPLYING = "APPLYING"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    CONFLICT = "CONFLICT"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class RuntimeOverrideDecision(StrEnum):
    ALLOWED = "ALLOWED"
    REJECTED = "REJECTED"
    NEEDS_DIFFERENT_BOUNDARY = "NEEDS_DIFFERENT_BOUNDARY"


@dataclass(frozen=True)
class RuntimeOverrideRequest:
    idempotency_key: str
    entity_type: str
    entity_id: str
    field: str
    old_value: str
    new_value: str
    reason: str
    expected_version: int
    expected_next_node: str | None = None


@dataclass(frozen=True)
class RuntimeOverrideCommand:
    override_id: str
    idempotency_key: str
    thread_id: str
    entity_type: str
    entity_id: str
    field: str
    old_value: str
    new_value: str
    reason: str
    expected_version: int
    expected_next_node: str | None
    operator_id: str
    operator_role: str
    operator_permissions: frozenset[str]
    requested_at: datetime

    def __post_init__(self) -> None:
        bounded_text = {
            "override_id": (self.override_id, 36),
            "idempotency_key": (self.idempotency_key, 128),
            "thread_id": (self.thread_id, 96),
            "entity_type": (self.entity_type, 32),
            "entity_id": (self.entity_id, 128),
            "field": (self.field, 64),
            "reason": (self.reason, 512),
            "operator_id": (self.operator_id, 128),
            "operator_role": (self.operator_role, 64),
        }
        for name, (value, limit) in bounded_text.items():
            if not value or len(value) > limit:
                raise ValueError(f"{name} must contain between 1 and {limit} characters")
        if self.expected_version < 0:
            raise ValueError("expected_version must not be negative")
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("requested_at must be timezone-aware")
        if self.expected_next_node is not None and not self.expected_next_node:
            raise ValueError("expected_next_node must be non-empty when provided")

    def to_fingerprint_dict(self) -> dict[str, object]:
        return {
            "thread_id": self.thread_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "field": self.field,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "reason": self.reason,
            "expected_version": self.expected_version,
            "expected_next_node": self.expected_next_node,
        }


@dataclass(frozen=True)
class OverridePolicyResult:
    decision: RuntimeOverrideDecision
    error_code: str | None = None

    @property
    def allowed(self) -> bool:
        return self.decision is RuntimeOverrideDecision.ALLOWED


@dataclass(frozen=True)
class RuntimeOverrideResult:
    override_id: str
    thread_id: str
    status: RuntimeOverrideStatus
    decision: RuntimeOverrideDecision | None
    before_version: int | None
    after_version: int | None
    source_checkpoint_id: str | None
    result_checkpoint_id: str | None
    entity_type: str
    entity_id: str
    field: str
    old_value: str
    new_value: str
    error_code: str | None = None
    error_summary: str | None = None
    event_status: str | None = None
    replayed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeOverrideError(Exception):
    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


class RuntimeOverrideIdempotencyConflict(RuntimeOverrideError):
    pass


@dataclass(frozen=True)
class StoredRuntimeOverride:
    override_id: str
    thread_id: str
    task_id: str
    idempotency_key: str
    payload_fingerprint: str
    operator_id: str
    operator_role: str
    status: RuntimeOverrideStatus
    decision: RuntimeOverrideDecision | None
    expected_version: int
    expected_next_node: str | None
    before_state_version: int | None
    after_state_version: int | None
    entity_type: str
    entity_id: str
    field: str
    old_value: str
    new_value: str
    reason: str
    source_checkpoint_id: str | None
    result_checkpoint_id: str | None
    event_status: str
    error_code: str | None
    error_summary: str | None
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    replayed: bool = False


@dataclass(frozen=True)
class UpdatedCheckpoint:
    record: CheckpointRecord
    next_nodes: tuple[str, ...]
