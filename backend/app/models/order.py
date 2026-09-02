from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("order_no", name="uq_orders_order_no"),
        Index("ix_orders_status_created_at", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    driver_id: Mapped[str | None] = mapped_column(String(64))
    vehicle_id: Mapped[str | None] = mapped_column(String(64))
    route_id: Mapped[str | None] = mapped_column(String(64))
    origin: Mapped[str] = mapped_column(String(255), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    cargo_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2, asdecimal=True))
    cargo_type: Mapped[str | None] = mapped_column(String(32))
    origin_station_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("logistics_stations.station_id", ondelete="RESTRICT"))
    destination_station_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("logistics_stations.station_id", ondelete="RESTRICT"))
