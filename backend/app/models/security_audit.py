from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.runtime_thread import BIGINT_PK


class SecurityAuditRecord(Base):
    __tablename__ = "security_audit_events"
    __table_args__ = (
        Index("ix_security_audit_created", "created_at"),
        Index("ix_security_audit_event_created", "event_type", "created_at"),
        Index("ix_security_audit_subject_created", "subject_id", "created_at"),
        Index("ix_security_audit_request", "request_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    permission: Mapped[str | None] = mapped_column(String(64))
    route_template: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    remote_ip: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

