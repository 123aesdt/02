from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class FleetDriver(TimestampMixin, Base):
    __tablename__ = "fleet_drivers"
    __table_args__ = (
        UniqueConstraint("driver_id", name="uq_fleet_drivers_driver_id"),
        Index("ix_fleet_drivers_status_node", "status", "current_node_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    license_class: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_vehicle_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("fleet_vehicles.vehicle_id", ondelete="RESTRICT"))
    current_node_id: Mapped[str] = mapped_column(String(64), ForeignKey("road_nodes.node_id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}
