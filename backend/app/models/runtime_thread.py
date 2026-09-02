from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, utc_now

BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")


class RuntimeThread(TimestampMixin, Base):
    __tablename__ = "runtime_threads"
    __table_args__ = (
        UniqueConstraint("thread_id", name="uq_runtime_threads_thread_id"),
        UniqueConstraint("task_id", name="uq_runtime_threads_task_id"),
        Index("ix_runtime_threads_status_updated", "status", "updated_at"),
        Index("ix_runtime_threads_current_checkpoint", "current_checkpoint_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(96), nullable=False)
    task_id: Mapped[str] = mapped_column(ForeignKey("dispatch_tasks.task_id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    current_checkpoint_id: Mapped[str | None] = mapped_column(String(64))
    state_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    current_node: Mapped[str | None] = mapped_column(String(32))
    next_node: Mapped[str | None] = mapped_column(String(32))
    checkpoint_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    checkpoint_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    last_event_sequence: Mapped[int | None] = mapped_column(BigInteger)
    worker_consumer: Mapped[str | None] = mapped_column(String(128))
    resumed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": row_version}


class RuntimeThreadEvent(Base):
    __tablename__ = "runtime_thread_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_runtime_thread_events_event_id"),
        UniqueConstraint("thread_id", "event_key", name="uq_runtime_thread_events_thread_event_key"),
        Index("ix_runtime_thread_events_thread_version", "thread_id", "state_version"),
        Index("ix_runtime_thread_events_thread_created", "thread_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_key: Mapped[str] = mapped_column(String(160), nullable=False)
    thread_id: Mapped[str] = mapped_column(ForeignKey("runtime_threads.thread_id", ondelete="RESTRICT"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    checkpoint_id: Mapped[str | None] = mapped_column(String(64))
    parent_checkpoint_id: Mapped[str | None] = mapped_column(String(64))
    state_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    node: Mapped[str | None] = mapped_column(String(32))
    next_node: Mapped[str | None] = mapped_column(String(32))
    checkpoint_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    worker_consumer: Mapped[str | None] = mapped_column(String(128))
    error_code: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
