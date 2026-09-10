from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RoadNode(TimestampMixin, Base):
    __tablename__ = "road_nodes"
    __table_args__ = (UniqueConstraint("node_id", name="uq_road_nodes_node_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    x_km: Mapped[Decimal] = mapped_column(Numeric(8, 2, asdecimal=True), nullable=False)
    y_km: Mapped[Decimal] = mapped_column(Numeric(8, 2, asdecimal=True), nullable=False)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)


class RoadEdge(TimestampMixin, Base):
    __tablename__ = "road_edges"
    __table_args__ = (
        UniqueConstraint("edge_id", name="uq_road_edges_edge_id"),
        Index("ix_road_edges_status_nodes", "status", "from_node_id", "to_node_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    edge_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    from_node_id: Mapped[str] = mapped_column(String(64), ForeignKey("road_nodes.node_id", ondelete="RESTRICT"), nullable=False)
    to_node_id: Mapped[str] = mapped_column(String(64), ForeignKey("road_nodes.node_id", ondelete="RESTRICT"), nullable=False)
    distance_km: Mapped[Decimal] = mapped_column(Numeric(8, 2, asdecimal=True), nullable=False)
    base_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    road_level: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    congestion_factor: Mapped[Decimal] = mapped_column(Numeric(5, 2, asdecimal=True), nullable=False, default=Decimal("1.00"))
    weight_limit_tons: Mapped[Decimal] = mapped_column(Numeric(6, 2, asdecimal=True), nullable=False)
    bidirectional: Mapped[bool] = mapped_column(Boolean, nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}
