from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Dispatch(TimestampMixin, Base):
    __tablename__ = "dispatches"
    __table_args__ = (UniqueConstraint("dispatch_no", name="uq_dispatches_dispatch_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dispatch_no: Mapped[str] = mapped_column(String(64), nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("dispatch_tasks.id", ondelete="RESTRICT"))
    original_driver_id: Mapped[str | None] = mapped_column(String(64))
    target_driver_id: Mapped[str | None] = mapped_column(String(64))
    original_route_id: Mapped[str | None] = mapped_column(String(64))
    target_route_id: Mapped[str | None] = mapped_column(String(64))
    original_vehicle_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("fleet_vehicles.vehicle_id", ondelete="RESTRICT"))
    target_vehicle_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("fleet_vehicles.vehicle_id", ondelete="RESTRICT"))
    transfer_node_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("road_nodes.node_id", ondelete="RESTRICT"))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    recommended_action: Mapped[str | None] = mapped_column(Text)
    analysis_mode: Mapped[str | None] = mapped_column(String(32))
    issue_subtype: Mapped[str | None] = mapped_column(String(32))
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
