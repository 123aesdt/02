from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DispatchPublication(Base):
    __tablename__ = "dispatch_publications"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_dispatch_publications_task_id"),
        UniqueConstraint("dispatch_id", name="uq_dispatch_publications_dispatch_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("dispatch_tasks.id", ondelete="RESTRICT"), nullable=False)
    dispatch_id: Mapped[int] = mapped_column(ForeignKey("dispatches.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PUBLISHED")
    route_id: Mapped[str | None] = mapped_column(String(64))
    route_instruction: Mapped[str | None] = mapped_column(Text)
    action_instruction: Mapped[str | None] = mapped_column(Text)
    published_by_subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    published_by_display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
