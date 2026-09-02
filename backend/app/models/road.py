from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RoadNode(TimestampMixin, Base):
    __tablename__ = "road_nodes"
    __table_args__ = (
        UniqueConstraint("node_id", name="uq_road_nodes_node_id"),
        Index("ix_road_nodes_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    node_name: Mapped[str] = mapped_column(String(128), nullable=False)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 6, asdecimal=True), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 6, asdecimal=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class RoadEdge(TimestampMixin, Base):
    __tablename__ = "road_edges"
    __table_args__ = (
        UniqueConstraint("edge_id", name="uq_road_edges_edge_id"),
        Index("ix_road_edges_status_nodes", "status", "from_node_id", "to_node_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    edge_id: Mapped[str] = mapped_column(String(64), nullable=False)
    from_node_id: Mapped[str] = mapped_column(String(64), ForeignKey("road_nodes.node_id", ondelete="RESTRICT"), nullable=False)
    to_node_id: Mapped[str] = mapped_column(String(64), ForeignKey("road_nodes.node_id", ondelete="RESTRICT"), nullable=False)
    road_name: Mapped[str] = mapped_column(String(128), nullable=False)
    distance_km: Mapped[Decimal] = mapped_column(Numeric(10, 2, asdecimal=True), nullable=False)
    estimated_duration_min: Mapped[Decimal] = mapped_column(Numeric(10, 2, asdecimal=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}
