from decimal import Decimal

from sqlalchemy import Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class LogisticsStation(TimestampMixin, Base):
    __tablename__ = "logistics_stations"
    __table_args__ = (
        UniqueConstraint("station_id", name="uq_logistics_stations_station_id"),
        Index("ix_logistics_stations_status_county", "status", "county"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[str] = mapped_column(String(64), nullable=False)
    station_name: Mapped[str] = mapped_column(String(128), nullable=False)
    station_type: Mapped[str] = mapped_column(String(32), nullable=False)
    county: Mapped[str] = mapped_column(String(64), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 6, asdecimal=True), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 6, asdecimal=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
