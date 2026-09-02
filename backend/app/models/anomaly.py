from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, utc_now


class Anomaly(TimestampMixin, Base):
    __tablename__ = "anomalies"
    __table_args__ = (
        UniqueConstraint("anomaly_no", name="uq_anomalies_anomaly_no"),
        UniqueConstraint("report_idempotency_key", name="uq_anomalies_report_idempotency_key"),
        Index("ix_anomalies_order_status", "order_id", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    anomaly_no: Mapped[str] = mapped_column(String(64), nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    anomaly_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reported_by_subject_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    source_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    location_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reported_vehicle_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    report_idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
