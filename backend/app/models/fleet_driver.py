from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class FleetDriver(TimestampMixin, Base):
    __tablename__ = "fleet_drivers"
    __table_args__ = (
        UniqueConstraint("driver_id", name="uq_fleet_drivers_driver_id"),
        UniqueConstraint("phone", name="uq_fleet_drivers_phone"),
        Index("ix_fleet_drivers_status_node", "status", "current_node_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[str] = mapped_column(String(64), nullable=False)
    driver_name: Mapped[str] = mapped_column(String(64), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    license_class: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_node_id: Mapped[str | None] = mapped_column(String(64))
