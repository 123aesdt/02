from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class RuntimeThreadStatus(StrEnum):
    RUNNING = "RUNNING"
    STABLE = "STABLE"
    OVERRIDING = "OVERRIDING"
    TERMINAL = "TERMINAL"


class RuntimeThreadEventType(StrEnum):
    THREAD_CREATED = "THREAD_CREATED"
    CHECKPOINT_STAGED = "CHECKPOINT_STAGED"
    CHECKPOINT_PROMOTED = "CHECKPOINT_PROMOTED"
    THREAD_RESUMED = "THREAD_RESUMED"
    THREAD_TERMINAL = "THREAD_TERMINAL"
    RECONCILIATION = "RECONCILIATION"
    ERROR = "ERROR"
    RUNTIME_OVERRIDE_APPLIED = "RUNTIME_OVERRIDE_APPLIED"


@dataclass(frozen=True)
class RuntimeThreadSnapshot:
    thread_id: str
    task_id: str
    status: RuntimeThreadStatus
    current_checkpoint_id: str | None
    state_version: int
    current_node: str | None
    next_node: str | None
    checkpoint_count: int
    checkpoint_size_bytes: int | None
    last_event_sequence: int | None
    worker_consumer: str | None
    resumed_count: int
    created_at: datetime
    updated_at: datetime
    terminal_at: datetime | None
    row_version: int

    @property
    def terminal(self) -> bool:
        return self.status is RuntimeThreadStatus.TERMINAL


@dataclass(frozen=True)
class RuntimeThreadEventSnapshot:
    event_id: str
    event_key: str
    thread_id: str
    event_type: RuntimeThreadEventType
    checkpoint_id: str | None
    parent_checkpoint_id: str | None
    state_version: int
    node: str | None
    next_node: str | None
    checkpoint_size_bytes: int | None
    worker_consumer: str | None
    error_code: str | None
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class PromoteCheckpoint:
    thread_id: str
    expected_checkpoint_id: str | None
    expected_state_version: int
    checkpoint_id: str
    parent_checkpoint_id: str | None
    node: str
    next_node: str | None
    checkpoint_size_bytes: int
    worker_consumer: str
    event_key: str
    event_type: RuntimeThreadEventType = RuntimeThreadEventType.CHECKPOINT_PROMOTED


@dataclass(frozen=True)
class CheckpointRecord:
    thread_id: str
    checkpoint_id: str
    parent_checkpoint_id: str | None
    checkpoint_namespace: str
    state: dict[str, Any]
    metadata: dict[str, Any]
    config: dict[str, Any]
    serialized_size_bytes: int


class ThreadVersionConflict(Exception):
    """Raised when a runtime-thread compare-and-swap loses a race."""


class BoundaryClaimConflict(Exception):
    """Raised when Worker or Override loses stable-boundary ownership."""


class CheckpointNotFound(Exception):
    """Raised when a canonical checkpoint payload is unavailable."""


class CheckpointPayloadTooLarge(Exception):
    """Raised before a checkpoint can become canonical."""
