from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.runtime_overrides.models import RuntimeOverrideRequest
from app.runtime_overrides.query_models import RuntimeInterventionContext


class CreateRuntimeOverrideRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    entity_type: str = Field(min_length=1, max_length=32)
    entity_id: str = Field(min_length=1, max_length=128)
    field: str = Field(min_length=1, max_length=64)
    old_value: str
    new_value: str
    reason: str = Field(min_length=1, max_length=512)
    expected_version: int = Field(ge=0)
    expected_next_node: str | None = Field(default=None, max_length=32)

    def to_request(self) -> RuntimeOverrideRequest:
        return RuntimeOverrideRequest(**self.model_dump())


class RuntimeOverrideResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    override_id: str
    thread_id: str
    task_id: str
    operator_id: str
    operator_role: str
    status: str
    decision: str | None
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
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    replayed: bool


class RuntimeInterventionTargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_type: str
    entity_id: str
    display_name: str
    field: str
    current_value: str
    allowed_new_values: list[str] | tuple[str, ...]


class RuntimeInterventionContextResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    thread_id: str
    task_id: str
    runtime_status: str
    state_version: int
    current_node: str | None
    next_node: str | None
    canonical_checkpoint_id: str | None
    checkpoint_available: bool
    eligibility: str
    eligibility_reason_code: str | None
    can_override: bool
    target: RuntimeInterventionTargetResponse | None
    observed_at: datetime

    @classmethod
    def from_context(cls, context: RuntimeInterventionContext):
        return cls.model_validate(context)


class RuntimeOverrideHistoryResponse(BaseModel):
    thread_id: str
    items: list[RuntimeOverrideResponse]
