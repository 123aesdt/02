import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.shared_memory.security import sanitize_audit_text, validate_safe_reference


class MemoryCategory(StrEnum):
    CHAT = "ChatMemory"
    LLM_WIKI = "LLMWiki"
    CODE_GRAPH = "CodeGraph"
    DISPATCH = "DispatchMemory"


class MemoryFactKind(StrEnum):
    ATTRIBUTE = "ATTRIBUTE"
    RELATIONSHIP = "RELATIONSHIP"
    EXPERIENCE = "EXPERIENCE"
    HYBRID = "HYBRID"


class MemoryTarget(StrEnum):
    VECTOR = "VECTOR"
    GRAPH = "GRAPH"


class MemoryFactStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    PENDING_REVIEW = "PENDING_REVIEW"
    CONFLICT = "CONFLICT"


class MutationDecision(StrEnum):
    CREATE = "CREATE"
    MERGE = "MERGE"
    REPLACE = "REPLACE"
    REJECT = "REJECT"
    CONFLICT_REVIEW = "CONFLICT_REVIEW"
    NOOP = "NOOP"


class MutationStatus(StrEnum):
    PENDING = "PENDING"
    APPLYING = "APPLYING"
    FINALIZING = "FINALIZING"
    APPLIED = "APPLIED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    CONFLICT = "CONFLICT"
    FAILED = "FAILED"


class ProjectionStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    STAGED = "STAGED"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
    FAILED = "FAILED"


def _enum(value: object, enum_type: type[StrEnum], field_name: str) -> StrEnum:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Unsupported {field_name}: {value!r}") from error


def _required_text(value: str, field_name: str, *, maximum: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{field_name} exceeds {maximum} characters")
    return normalized


def _optional_text(value: str | None, field_name: str, *, maximum: int) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise ValueError(f"{field_name} exceeds {maximum} characters")
    return normalized


def _aware(value: datetime | None, field_name: str) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _canonical_size(value: object) -> int:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("value_json must be JSON serializable with finite numbers") from error
    return len(encoded)


@dataclass(frozen=True)
class SharedMemoryMutationCommand:
    idempotency_key: str
    category: MemoryCategory | str
    fact_kind: MemoryFactKind | str
    subject_type: str
    subject_id: str
    predicate: str
    value_json: dict[str, Any]
    confidence: Decimal
    incoming_at: datetime
    source_type: str
    source_id: str
    operator_id: str
    human_confirmed: bool
    reason: str
    targets: frozenset[MemoryTarget | str]
    object_type: str | None = None
    object_id: str | None = None
    expected_version: int | None = None
    expires_at: datetime | None = None
    evidence_text: str | None = None
    evidence_ref: str | None = None
    evidence_observed_at: datetime | None = None
    vector_memory_id: str | None = None
    graph_fact_key: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "category", _enum(self.category, MemoryCategory, "memory category"))
        object.__setattr__(self, "fact_kind", _enum(self.fact_kind, MemoryFactKind, "memory fact kind"))
        normalized_targets = frozenset(_enum(value, MemoryTarget, "memory target") for value in self.targets)
        if not normalized_targets:
            raise ValueError("targets must not be empty")
        object.__setattr__(self, "targets", normalized_targets)

        for name, maximum in (
            ("idempotency_key", 128),
            ("subject_type", 64),
            ("subject_id", 128),
            ("predicate", 64),
            ("source_type", 64),
            ("source_id", 128),
            ("operator_id", 128),
            ("reason", 512),
        ):
            object.__setattr__(self, name, _required_text(getattr(self, name), name, maximum=maximum))

        for name, maximum in (
            ("object_type", 64),
            ("object_id", 128),
            ("evidence_text", 2000),
            ("evidence_ref", 512),
            ("vector_memory_id", 128),
            ("graph_fact_key", 255),
        ):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name, maximum=maximum))

        object.__setattr__(self, "reason", sanitize_audit_text(self.reason))
        object.__setattr__(self, "evidence_text", sanitize_audit_text(self.evidence_text))
        object.__setattr__(self, "evidence_ref", validate_safe_reference(self.evidence_ref))

        confidence = Decimal(str(self.confidence))
        if not confidence.is_finite() or not Decimal("0") <= confidence <= Decimal("1"):
            raise ValueError("confidence must be finite and between 0 and 1")
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "incoming_at", _aware(self.incoming_at, "incoming_at"))
        object.__setattr__(self, "expires_at", _aware(self.expires_at, "expires_at"))
        object.__setattr__(
            self,
            "evidence_observed_at",
            _aware(self.evidence_observed_at, "evidence_observed_at"),
        )

        if self.expected_version is not None and self.expected_version < 1:
            raise ValueError("expected_version must be positive")
        if not self.evidence_text and not self.evidence_ref:
            raise ValueError("evidence_text or evidence_ref is required")
        if self.fact_kind in {MemoryFactKind.RELATIONSHIP, MemoryFactKind.HYBRID}:
            if not self.object_type or not self.object_id:
                raise ValueError("object_type and object_id are required for relationship facts")
        if _canonical_size(self.value_json) > 16 * 1024:
            raise ValueError("value_json exceeds 16 KiB")
        copied_value = json.loads(
            json.dumps(self.value_json, ensure_ascii=False, allow_nan=False)
        )
        object.__setattr__(self, "value_json", copied_value)

        proposed_size = len(
            json.dumps(
                self.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        )
        if proposed_size > 32 * 1024:
            raise ValueError("proposed_fact_json exceeds 32 KiB")

    def fact_identity(self) -> dict[str, object]:
        identity: dict[str, object] = {
            "category": self.category.value,
            "fact_kind": self.fact_kind.value,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "predicate": self.predicate,
        }
        if self.fact_kind in {MemoryFactKind.RELATIONSHIP, MemoryFactKind.HYBRID}:
            identity.update(object_type=self.object_type, object_id=self.object_id)
        elif self.fact_kind is MemoryFactKind.EXPERIENCE:
            identity.update(object_type=self.object_type, object_id=self.object_id)
        return identity

    def to_dict(self) -> dict[str, object]:
        return {
            "idempotency_key": self.idempotency_key,
            "category": self.category.value,
            "fact_kind": self.fact_kind.value,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "predicate": self.predicate,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "value_json": dict(self.value_json),
            "expected_version": self.expected_version,
            "confidence": format(self.confidence, "f"),
            "incoming_at": self.incoming_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "operator_id": self.operator_id,
            "human_confirmed": self.human_confirmed,
            "reason": self.reason,
            "evidence_text": self.evidence_text,
            "evidence_ref": self.evidence_ref,
            "evidence_observed_at": (
                self.evidence_observed_at.isoformat() if self.evidence_observed_at else None
            ),
            "vector_memory_id": self.vector_memory_id,
            "graph_fact_key": self.graph_fact_key,
            "targets": sorted(target.value for target in self.targets),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "SharedMemoryMutationCommand":
        return cls(
            idempotency_key=str(value["idempotency_key"]),
            category=str(value["category"]),
            fact_kind=str(value["fact_kind"]),
            subject_type=str(value["subject_type"]),
            subject_id=str(value["subject_id"]),
            predicate=str(value["predicate"]),
            object_type=str(value["object_type"]) if value.get("object_type") else None,
            object_id=str(value["object_id"]) if value.get("object_id") else None,
            value_json=dict(value["value_json"]),
            expected_version=(
                int(value["expected_version"])
                if value.get("expected_version") is not None
                else None
            ),
            confidence=Decimal(str(value["confidence"])),
            incoming_at=datetime.fromisoformat(str(value["incoming_at"])),
            expires_at=(
                datetime.fromisoformat(str(value["expires_at"]))
                if value.get("expires_at")
                else None
            ),
            source_type=str(value["source_type"]),
            source_id=str(value["source_id"]),
            operator_id=str(value["operator_id"]),
            human_confirmed=bool(value["human_confirmed"]),
            reason=str(value["reason"]),
            evidence_text=(str(value["evidence_text"]) if value.get("evidence_text") else None),
            evidence_ref=str(value["evidence_ref"]) if value.get("evidence_ref") else None,
            evidence_observed_at=(
                datetime.fromisoformat(str(value["evidence_observed_at"]))
                if value.get("evidence_observed_at")
                else None
            ),
            vector_memory_id=(
                str(value["vector_memory_id"]) if value.get("vector_memory_id") else None
            ),
            graph_fact_key=(
                str(value["graph_fact_key"]) if value.get("graph_fact_key") else None
            ),
            targets=frozenset(str(target) for target in value["targets"]),
        )


@dataclass(frozen=True)
class MemoryMutationResult:
    mutation_id: str
    fact_key: str
    decision: MutationDecision
    status: MutationStatus
    before_version: int | None
    after_version: int | None
    vector_status: ProjectionStatus
    graph_status: ProjectionStatus
    projection_incomplete: bool = False
    error_code: str | None = None
    error_summary: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "mutation_id": self.mutation_id,
            "fact_key": self.fact_key,
            "decision": self.decision.value,
            "status": self.status.value,
            "before_version": self.before_version,
            "after_version": self.after_version,
            "vector_status": self.vector_status.value,
            "graph_status": self.graph_status.value,
            "projection_incomplete": self.projection_incomplete,
            "error_code": self.error_code,
            "error_summary": self.error_summary,
            "metadata": dict(self.metadata),
        }
