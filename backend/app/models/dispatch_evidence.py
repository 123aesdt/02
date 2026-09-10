from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DispatchEvidence(TimestampMixin, Base):
    __tablename__ = "dispatch_evidence"
    __table_args__ = (Index("ix_dispatch_evidence_dispatch_type", "dispatch_id", "evidence_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dispatch_id: Mapped[int] = mapped_column(ForeignKey("dispatches.id", ondelete="CASCADE"), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    road_network_version: Mapped[int | None] = mapped_column(Integer)
