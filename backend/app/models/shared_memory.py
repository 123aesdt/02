from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")


class MemoryMutation(TimestampMixin, Base):
    __tablename__ = "memory_mutations"
    __table_args__ = (
        UniqueConstraint("mutation_id", name="uq_memory_mutations_mutation_id"),
        UniqueConstraint("idempotency_key", name="uq_memory_mutations_idempotency_key"),
        Index("ix_memory_mutations_fact_created", "fact_key", "created_at"),
        Index("ix_memory_mutations_status", "status"),
        Index("ix_memory_mutations_projection_status", "vector_status", "graph_status"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    mutation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    fact_key: Mapped[str] = mapped_column(String(68), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    fact_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    operator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    expected_version: Mapped[int | None] = mapped_column(Integer)
    incoming_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    incoming_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    human_confirmed: Mapped[bool] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    targets_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    proposed_fact_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    decision: Mapped[str | None] = mapped_column(String(32))
    reason_code: Mapped[str | None] = mapped_column(String(64))
    before_version: Mapped[int | None] = mapped_column(Integer)
    after_version: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    vector_status: Mapped[str] = mapped_column(String(32), nullable=False)
    graph_status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_summary: Mapped[str | None] = mapped_column(String(512))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SharedMemoryFact(TimestampMixin, Base):
    __tablename__ = "shared_memory_facts"
    __table_args__ = (
        UniqueConstraint("fact_id", name="uq_shared_memory_facts_fact_id"),
        UniqueConstraint("fact_key", name="uq_shared_memory_facts_fact_key"),
        Index("ix_shared_memory_facts_category_status", "category", "status"),
        Index(
            "ix_shared_memory_facts_subject_predicate",
            "subject_type",
            "subject_id",
            "predicate",
        ),
        Index("ix_shared_memory_facts_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    fact_id: Mapped[str] = mapped_column(String(36), nullable=False)
    fact_key: Mapped[str] = mapped_column(String(68), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    fact_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    predicate: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(64))
    object_id: Mapped[str | None] = mapped_column(String(128))
    value_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vector_memory_id: Mapped[str | None] = mapped_column(String(128))
    graph_fact_key: Mapped[str | None] = mapped_column(String(255))
    last_mutation_id: Mapped[str] = mapped_column(String(36), nullable=False)

    __mapper_args__ = {"version_id_col": version}


class MemoryEvidence(Base):
    __tablename__ = "memory_evidence"
    __table_args__ = (
        UniqueConstraint("evidence_id", name="uq_memory_evidence_evidence_id"),
        UniqueConstraint(
            "mutation_id",
            "evidence_fingerprint",
            name="uq_memory_evidence_mutation_fingerprint",
        ),
        Index("ix_memory_evidence_fact_id", "fact_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    evidence_id: Mapped[str] = mapped_column(String(36), nullable=False)
    mutation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("memory_mutations.mutation_id", ondelete="RESTRICT"),
        nullable=False,
    )
    fact_id: Mapped[str | None] = mapped_column(String(36))
    evidence_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_text: Mapped[str | None] = mapped_column(Text)
    evidence_ref: Mapped[str | None] = mapped_column(String(512))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    safe_summary: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MemoryMutationAttempt(Base):
    __tablename__ = "memory_mutation_attempts"
    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_memory_mutation_attempts_attempt_id"),
        UniqueConstraint(
            "mutation_id",
            "attempt_no",
            name="uq_memory_mutation_attempts_mutation_attempt",
        ),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    attempt_id: Mapped[str] = mapped_column(String(36), nullable=False)
    mutation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("memory_mutations.mutation_id", ondelete="RESTRICT"),
        nullable=False,
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vector_before: Mapped[str] = mapped_column(String(32), nullable=False)
    vector_after: Mapped[str] = mapped_column(String(32), nullable=False)
    graph_before: Mapped[str] = mapped_column(String(32), nullable=False)
    graph_after: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_summary: Mapped[str | None] = mapped_column(String(512))

