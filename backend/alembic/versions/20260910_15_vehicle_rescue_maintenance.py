"""add vehicle rescue maintenance workflow"""

import sqlalchemy as sa

from alembic import op

revision = "20260910_15"
down_revision = "20260907_14"
branch_labels = None
depends_on = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    with op.batch_alter_table("fleet_vehicles") as batch:
        batch.add_column(sa.Column("fault_code", sa.String(length=64)))
        batch.add_column(sa.Column("status_reason", sa.String(length=255)))
        batch.add_column(sa.Column("status_changed_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("available_after", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("maintenance_order_no", sa.String(length=64)))

    op.create_table(
        "rescue_units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("unit_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("plate_no", sa.String(length=32), nullable=False),
        sa.Column("unit_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_node_id", sa.String(length=64), nullable=False),
        sa.Column("capacity_tons", sa.Numeric(6, 2, asdecimal=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["current_node_id"], ["road_nodes.node_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("unit_id", name="uq_rescue_units_unit_id"),
        sa.UniqueConstraint("plate_no", name="uq_rescue_units_plate_no"),
    )
    op.create_index("ix_rescue_units_status_node", "rescue_units", ["status", "current_node_id"])
    op.create_table(
        "maintenance_bays",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bay_code", sa.String(length=32), nullable=False),
        sa.Column("station_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_order_no", sa.String(length=64)),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["station_id"], ["logistics_stations.station_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("bay_code", name="uq_maintenance_bays_bay_code"),
    )
    op.create_index("ix_maintenance_bays_station_status", "maintenance_bays", ["station_id", "status"])
    op.create_table(
        "rescue_missions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mission_no", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("vehicle_id", sa.String(length=64), nullable=False),
        sa.Column("rescue_unit_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("incident_node_id", sa.String(length=64), nullable=False),
        sa.Column("station_node_id", sa.String(length=64), nullable=False),
        sa.Column("outbound_edge_ids", sa.JSON(), nullable=False),
        sa.Column("tow_edge_ids", sa.JSON(), nullable=False),
        sa.Column("next_transition_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["task_id"], ["dispatch_tasks.task_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["fleet_vehicles.vehicle_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rescue_unit_id"], ["rescue_units.unit_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["incident_node_id"], ["road_nodes.node_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["station_node_id"], ["road_nodes.node_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("mission_no", name="uq_rescue_missions_mission_no"),
        sa.UniqueConstraint("task_id", name="uq_rescue_missions_task_id"),
    )
    op.create_index("ix_rescue_missions_due", "rescue_missions", ["status", "next_transition_at"])
    op.create_table(
        "maintenance_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_no", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("vehicle_id", sa.String(length=64), nullable=False),
        sa.Column("bay_code", sa.String(length=32)),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("fault_code", sa.String(length=64), nullable=False),
        sa.Column("diagnosis", sa.Text()),
        sa.Column("repair_minutes", sa.Integer(), nullable=False),
        sa.Column("manual_inspection_required", sa.Boolean(), nullable=False),
        sa.Column("inspection_result", sa.String(length=32)),
        sa.Column("next_transition_at", sa.DateTime(timezone=True)),
        sa.Column("available_after", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["task_id"], ["dispatch_tasks.task_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["fleet_vehicles.vehicle_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["bay_code"], ["maintenance_bays.bay_code"], ondelete="RESTRICT"),
        sa.UniqueConstraint("order_no", name="uq_maintenance_orders_order_no"),
        sa.UniqueConstraint("task_id", name="uq_maintenance_orders_task_id"),
    )
    op.create_index("ix_maintenance_orders_due", "maintenance_orders", ["status", "next_transition_at"])
    op.create_table(
        "vehicle_status_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vehicle_id", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=False),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vehicle_id"], ["fleet_vehicles.vehicle_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["dispatch_tasks.task_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_vehicle_status_history_vehicle_changed", "vehicle_status_history", ["vehicle_id", "changed_at"])
    op.create_table(
        "domain_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("aggregate_type", sa.String(length=32), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=255)),
        sa.ForeignKeyConstraint(["task_id"], ["dispatch_tasks.task_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("event_id", name="uq_domain_outbox_event_id"),
    )
    op.create_index("ix_domain_outbox_unpublished", "domain_outbox", ["published_at", "id"])


def downgrade() -> None:
    for index_name, table_name in (
        ("ix_domain_outbox_unpublished", "domain_outbox"),
        ("ix_vehicle_status_history_vehicle_changed", "vehicle_status_history"),
        ("ix_maintenance_orders_due", "maintenance_orders"),
        ("ix_rescue_missions_due", "rescue_missions"),
        ("ix_maintenance_bays_station_status", "maintenance_bays"),
        ("ix_rescue_units_status_node", "rescue_units"),
    ):
        op.drop_index(index_name, table_name=table_name)
        op.drop_table(table_name)
    with op.batch_alter_table("fleet_vehicles") as batch:
        for column_name in ("maintenance_order_no", "available_after", "status_changed_at", "status_reason", "fault_code"):
            batch.drop_column(column_name)
