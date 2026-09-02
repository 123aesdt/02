from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.graph_memory.models import GraphEntity, RelationType
from app.shared_memory.models import SharedMemoryMutationCommand


@dataclass(frozen=True)
class MemoryFingerprints:
    fact_key: str
    content_fingerprint: str
    payload_fingerprint: str
    evidence_fingerprint: str


@dataclass(frozen=True)
class BeginMutationResult:
    mutation_id: str
    replayed: bool
    payload_fingerprint: str


@dataclass(frozen=True)
class StoredMutation:
    mutation_id: str
    fact_key: str
    decision: str | None
    reason_code: str | None
    status: str
    before_version: int | None
    after_version: int | None
    vector_status: str
    graph_status: str
    error_code: str | None
    error_summary: str | None
    proposed_fact_json: dict[str, object]


@dataclass(frozen=True)
class VectorProjection:
    mutation_id: str
    fact_key: str
    control_version: int
    memory_id: str
    vector: tuple[float, ...]
    driver_id: str
    route_id: str
    anomaly_type: str
    resolution_text: str
    metadata: dict[str, object] = field(default_factory=dict)
    expires_at: datetime | None = None


@dataclass(frozen=True)
class GraphProjection:
    mutation_id: str
    fact_key: str
    control_version: int
    source: GraphEntity
    relation_type: RelationType
    target: GraphEntity
    confidence: Decimal
    source_type: str
    evidence: str | None
    expires_at: datetime | None
    timestamp: datetime


class MemoryControlRepository(Protocol):
    def begin_or_replay(
        self,
        command: SharedMemoryMutationCommand,
        fingerprints: MemoryFingerprints,
    ) -> BeginMutationResult: ...
