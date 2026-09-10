from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RescueUnit(TimestampMixin, Base):
    __tablename__ = "rescue_units"
    __table_args__ = (
        UniqueConstraint("unit_id", name="uq_rescue_units_unit_id"),
        UniqueConstraint("plate_no", name="uq_rescue_units_plate_no"),
        Index("ix_rescue_units_status_node", "status", "current_node_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    plate_no: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_node_id: Mapped[str] = mapped_column(String(64), ForeignKey("road_nodes.node_id", ondelete="RESTRICT"), nullable=False)
    capacity_tons: Mapped[Decimal] = mapped_column(Numeric(6, 2, asdecimal=True), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}


class RescueMission(TimestampMixin, Base):
    __tablename__ = "rescue_missions"
    __table_args__ = (
        UniqueConstraint("mission_no", name="uq_rescue_missions_mission_no"),
        UniqueConstraint("task_id", name="uq_rescue_missions_task_id"),
        Index("ix_rescue_missions_due", "status", "next_transition_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    mission_no: Mapped[str] = mapped_column(String(64), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("dispatch_tasks.task_id", ondelete="CASCADE"), nullable=False)
    vehicle_id: Mapped[str] = mapped_column(String(64), ForeignKey("fleet_vehicles.vehicle_id", ondelete="RESTRICT"), nullable=False)
    rescue_unit_id: Mapped[str] = mapped_column(String(64), ForeignKey("rescue_units.unit_id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    incident_node_id: Mapped[str] = mapped_column(String(64), ForeignKey("road_nodes.node_id", ondelete="RESTRICT"), nullable=False)
    station_node_id: Mapped[str] = mapped_column(String(64), ForeignKey("road_nodes.node_id", ondelete="RESTRICT"), nullable=False)
    outbound_edge_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    tow_edge_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    next_transition_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}


class MaintenanceBay(TimestampMixin, Base):
    __tablename__ = "maintenance_bays"
    __table_args__ = (
        UniqueConstraint("bay_code", name="uq_maintenance_bays_bay_code"),
        Index("ix_maintenance_bays_station_status", "station_id", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    bay_code: Mapped[str] = mapped_column(String(32), nullable=False)
    station_id: Mapped[str] = mapped_column(String(64), ForeignKey("logistics_stations.station_id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_order_no: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}


class MaintenanceOrder(TimestampMixin, Base):
    __tablename__ = "maintenance_orders"
    __table_args__ = (
        UniqueConstraint("order_no", name="uq_maintenance_orders_order_no"),
        UniqueConstraint("task_id", name="uq_maintenance_orders_task_id"),
        Index("ix_maintenance_orders_due", "status", "next_transition_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(String(64), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("dispatch_tasks.task_id", ondelete="CASCADE"), nullable=False)
    vehicle_id: Mapped[str] = mapped_column(String(64), ForeignKey("fleet_vehicles.vehicle_id", ondelete="RESTRICT"), nullable=False)
    bay_code: Mapped[str | None] = mapped_column(String(32), ForeignKey("maintenance_bays.bay_code", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    fault_code: Mapped[str] = mapped_column(String(64), nullable=False)
    diagnosis: Mapped[str | None] = mapped_column(Text)
    repair_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    manual_inspection_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    inspection_result: Mapped[str | None] = mapped_column(String(32))
    next_transition_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}


class VehicleStatusHistory(Base):
    __tablename__ = "vehicle_status_history"
    __table_args__ = (Index("ix_vehicle_status_history_vehicle_changed", "vehicle_id", "changed_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(String(64), ForeignKey("fleet_vehicles.vehicle_id", ondelete="RESTRICT"), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("dispatch_tasks.task_id", ondelete="CASCADE"), nullable=False)
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DomainOutbox(Base):
    __tablename__ = "domain_outbox"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_domain_outbox_event_id"),
        Index("ix_domain_outbox_unpublished", "published_at", "id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("dispatch_tasks.task_id", ondelete="CASCADE"), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(255))
