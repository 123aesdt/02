from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AuditRecord(TimestampMixin, Base):
    __tablename__ = "audit_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("dispatch_tasks.id", ondelete="RESTRICT"), nullable=False)
    dispatch_id: Mapped[int] = mapped_column(ForeignKey("dispatches.id", ondelete="RESTRICT"), nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
