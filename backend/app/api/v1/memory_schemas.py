from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.shared_memory.models import SharedMemoryMutationCommand


class CreateMemoryMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str
    category: str
    fact_kind: str
    subject_type: str
    subject_id: str
    predicate: str
    value_json: dict[str, object]
    confidence: Decimal
    incoming_at: datetime
    source_type: str
    source_id: str
    human_confirmed: bool = False
    reason: str
    targets: frozenset[str]
    object_type: str | None = None
    object_id: str | None = None
    expected_version: int | None = None
    expires_at: datetime | None = None
    evidence_text: str | None = Field(default=None, max_length=2_000)
    evidence_ref: str | None = Field(default=None, max_length=512)
    evidence_observed_at: datetime | None = None
    vector_memory_id: str | None = None
    graph_fact_key: str | None = None

    def to_command(self, *, operator_id: str) -> SharedMemoryMutationCommand:
        return SharedMemoryMutationCommand(**self.model_dump(), operator_id=operator_id)


class MemoryMutationResponse(BaseModel):
    mutation_id: str
    fact_key: str
    decision: str
    status: str
    before_version: int | None
    after_version: int | None
    vector_status: str
    graph_status: str
    projection_incomplete: bool
    error_code: str | None = None
    error_summary: str | None = Field(default=None, max_length=512)
