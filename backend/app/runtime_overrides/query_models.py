from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RuntimeInterventionEligibility(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    NOT_STABLE = "NOT_STABLE"
    TERMINAL = "TERMINAL"
    NO_PERMISSION = "NO_PERMISSION"
    WRONG_BOUNDARY = "WRONG_BOUNDARY"
    BUSY = "BUSY"


@dataclass(frozen=True)
class RuntimeInterventionTarget:
    entity_type: str
    entity_id: str
    display_name: str
    field: str
    current_value: str
    allowed_new_values: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeInterventionContext:
    thread_id: str
    task_id: str
    runtime_status: str
    state_version: int
    current_node: str | None
    next_node: str | None
    canonical_checkpoint_id: str | None
    checkpoint_available: bool
    eligibility: RuntimeInterventionEligibility
    eligibility_reason_code: str | None
    can_override: bool
    target: RuntimeInterventionTarget | None
    observed_at: datetime

