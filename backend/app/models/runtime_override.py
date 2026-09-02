from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, utc_now
from app.models.runtime_thread import BIGINT_PK


class RuntimeOverride(TimestampMixin, Base):
    __tablename__ = "runtime_overrides"
    __table_args__ = (
        UniqueConstraint("override_id", name="uq_runtime_overrides_override_id"),
        UniqueConstraint("idempotency_key", name="uq_runtime_overrides_idempotency_key"),
        Index("ix_runtime_overrides_thread_status_expiry", "thread_id", "status", "intent_expires_at"),
        Index("ix_runtime_overrides_thread_requested", "thread_id", "requested_at"),
        Index("ix_runtime_overrides_result_checkpoint", "result_checkpoint_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    override_id: Mapped[str] = mapped_column(String(36), nullable=False)
    thread_id: Mapped[str] = mapped_column(ForeignKey("runtime_threads.thread_id", ondelete="RESTRICT"), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    operator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    operator_role: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_next_node: Mapped[str | None] = mapped_column(String(32))
    before_state_version: Mapped[int | None] = mapped_column(BigInteger)
    after_state_version: Mapped[int | None] = mapped_column(BigInteger)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value_json: Mapped[object] = mapped_column(JSON, nullable=False)
    new_value_json: Mapped[object] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    decision: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    source_checkpoint_id: Mapped[str | None] = mapped_column(String(64))
    result_checkpoint_id: Mapped[str | None] = mapped_column(String(64))
    event_status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    intent_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_summary: Mapped[str | None] = mapped_column(String(512))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RuntimeOverrideAttempt(Base):
    __tablename__ = "runtime_override_attempts"
    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_runtime_override_attempts_attempt_id"),
        UniqueConstraint("override_id", "attempt_no", name="uq_runtime_override_attempts_override_attempt"),
        Index("ix_runtime_override_attempts_override_created", "override_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    attempt_id: Mapped[str] = mapped_column(String(36), nullable=False)
    override_id: Mapped[str] = mapped_column(ForeignKey("runtime_overrides.override_id", ondelete="RESTRICT"), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_state_version: Mapped[int | None] = mapped_column(BigInteger)
    source_checkpoint_id: Mapped[str | None] = mapped_column(String(64))
    result_checkpoint_id: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_summary: Mapped[str | None] = mapped_column(String(512))
    authorization_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    lock_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    checkpoint_read_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    state_update_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    promotion_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    total_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
