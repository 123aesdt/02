from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DispatchTask(TimestampMixin, Base):
    __tablename__ = "dispatch_tasks"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_dispatch_tasks_task_id"),
        UniqueConstraint("idempotency_key", name="uq_dispatch_tasks_idempotency_key"),
        Index("ix_dispatch_tasks_status_created_at", "status", "created_at"),
        Index("ix_dispatch_tasks_assignee_created_at", "assignee_subject_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    anomaly_id: Mapped[int | None] = mapped_column(ForeignKey("anomalies.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    assignee_subject_id: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
