from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class LogisticsStation(TimestampMixin, Base):
    __tablename__ = "logistics_stations"
    __table_args__ = (
        UniqueConstraint("station_id", name="uq_logistics_stations_station_id"),
        Index("ix_logistics_stations_status_node", "status", "road_node_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    station_type: Mapped[str] = mapped_column(String(32), nullable=False)
    road_node_id: Mapped[str] = mapped_column(String(64), ForeignKey("road_nodes.node_id", ondelete="RESTRICT"), nullable=False)
    handling_capacity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2, asdecimal=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
