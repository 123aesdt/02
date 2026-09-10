from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class FleetVehicle(TimestampMixin, Base):
    __tablename__ = "fleet_vehicles"
    __table_args__ = (
        UniqueConstraint("vehicle_id", name="uq_fleet_vehicles_vehicle_id"),
        UniqueConstraint("plate_no", name="uq_fleet_vehicles_plate_no"),
        Index("ix_fleet_vehicles_status_node", "status", "current_node_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(String(64), nullable=False)
    plate_no: Mapped[str] = mapped_column(String(32), nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String(32), nullable=False)
    max_load_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2, asdecimal=True), nullable=False)
    current_load_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2, asdecimal=True), nullable=False)
    cargo_capability: Mapped[str] = mapped_column(String(32), nullable=False)
    gross_weight_tons: Mapped[Decimal] = mapped_column(Numeric(6, 2, asdecimal=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    fault_code: Mapped[str | None] = mapped_column(String(64))
    status_reason: Mapped[str | None] = mapped_column(String(255))
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    maintenance_order_no: Mapped[str | None] = mapped_column(String(64))
    current_node_id: Mapped[str] = mapped_column(String(64), ForeignKey("road_nodes.node_id", ondelete="RESTRICT"), nullable=False)
    assigned_driver_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("fleet_drivers.driver_id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}
