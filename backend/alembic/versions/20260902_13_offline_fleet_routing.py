"""add offline fleet, road, and dispatch evidence schema"""

import sqlalchemy as sa

from alembic import op

revision = "20260902_13"
down_revision = "20260901_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "logistics_stations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("station_id", sa.String(length=64), nullable=False),
        sa.Column("station_name", sa.String(length=128), nullable=False),
        sa.Column("station_type", sa.String(length=32), nullable=False),
        sa.Column("county", sa.String(length=64), nullable=False),
        sa.Column("longitude", sa.Numeric(10, 6, asdecimal=True), nullable=False),
        sa.Column("latitude", sa.Numeric(10, 6, asdecimal=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("station_id", name="uq_logistics_stations_station_id"),
    )
    op.create_index("ix_logistics_stations_status_county", "logistics_stations", ["status", "county"])
    op.create_table(
        "fleet_drivers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("driver_id", sa.String(length=64), nullable=False),
        sa.Column("driver_name", sa.String(length=64), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("license_class", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_node_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("driver_id", name="uq_fleet_drivers_driver_id"),
        sa.UniqueConstraint("phone", name="uq_fleet_drivers_phone"),
    )
    op.create_index("ix_fleet_drivers_status_node", "fleet_drivers", ["status", "current_node_id"])
    op.create_table(
        "road_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("node_name", sa.String(length=128), nullable=False),
        sa.Column("node_type", sa.String(length=32), nullable=False),
        sa.Column("longitude", sa.Numeric(10, 6, asdecimal=True), nullable=False),
        sa.Column("latitude", sa.Numeric(10, 6, asdecimal=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("node_id", name="uq_road_nodes_node_id"),
    )
    op.create_index("ix_road_nodes_status", "road_nodes", ["status"])
    op.create_table(
        "fleet_vehicles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vehicle_id", sa.String(length=64), nullable=False),
        sa.Column("plate_no", sa.String(length=32), nullable=False),
        sa.Column("vehicle_type", sa.String(length=32), nullable=False),
        sa.Column("max_load_kg", sa.Numeric(10, 2, asdecimal=True), nullable=False),
        sa.Column("current_load_kg", sa.Numeric(10, 2, asdecimal=True), nullable=False),
        sa.Column("cargo_capability", sa.String(length=32), nullable=False),
        sa.Column("gross_weight_tons", sa.Numeric(6, 2, asdecimal=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_node_id", sa.String(length=64), nullable=False),
        sa.Column("assigned_driver_id", sa.String(length=64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["current_node_id"], ["road_nodes.node_id"], name="fk_fleet_vehicles_current_node_id_road_nodes", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["assigned_driver_id"], ["fleet_drivers.driver_id"], name="fk_fleet_vehicles_assigned_driver_id_fleet_drivers", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("vehicle_id", name="uq_fleet_vehicles_vehicle_id"),
        sa.UniqueConstraint("plate_no", name="uq_fleet_vehicles_plate_no"),
    )
    op.create_index("ix_fleet_vehicles_status_node", "fleet_vehicles", ["status", "current_node_id"])
    op.create_table(
        "road_edges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("edge_id", sa.String(length=64), nullable=False),
        sa.Column("from_node_id", sa.String(length=64), nullable=False),
        sa.Column("to_node_id", sa.String(length=64), nullable=False),
        sa.Column("road_name", sa.String(length=128), nullable=False),
        sa.Column("distance_km", sa.Numeric(10, 2, asdecimal=True), nullable=False),
        sa.Column("estimated_duration_min", sa.Numeric(10, 2, asdecimal=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["from_node_id"], ["road_nodes.node_id"], name="fk_road_edges_from_node_id_road_nodes", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["to_node_id"], ["road_nodes.node_id"], name="fk_road_edges_to_node_id_road_nodes", ondelete="RESTRICT"),
        sa.UniqueConstraint("edge_id", name="uq_road_edges_edge_id"),
    )
    op.create_index("ix_road_edges_status_nodes", "road_edges", ["status", "from_node_id", "to_node_id"])
    op.create_table(
        "dispatch_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dispatch_id", sa.Integer(), nullable=False),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("evidence_source", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4, asdecimal=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dispatch_id"], ["dispatches.id"], name="fk_dispatch_evidence_dispatch_id_dispatches", ondelete="CASCADE"),
    )
    op.create_index("ix_dispatch_evidence_dispatch_type", "dispatch_evidence", ["dispatch_id", "evidence_type"])

    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column("cargo_weight_kg", sa.Numeric(10, 2, asdecimal=True), nullable=True))
        batch.add_column(sa.Column("cargo_type", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("origin_station_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("destination_station_id", sa.String(length=64), nullable=True))
        batch.create_foreign_key(
            "fk_orders_origin_station_id_logistics_stations",
            "logistics_stations",
            ["origin_station_id"],
            ["station_id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_orders_destination_station_id_logistics_stations",
            "logistics_stations",
            ["destination_station_id"],
            ["station_id"],
            ondelete="RESTRICT",
        )
    with op.batch_alter_table("anomalies") as batch:
        batch.add_column(sa.Column("incident_node_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("affected_edge_id", sa.String(length=64), nullable=True))
        batch.create_foreign_key(
            "fk_anomalies_incident_node_id_road_nodes",
            "road_nodes",
            ["incident_node_id"],
            ["node_id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_anomalies_affected_edge_id_road_edges",
            "road_edges",
            ["affected_edge_id"],
            ["edge_id"],
            ondelete="RESTRICT",
        )
    with op.batch_alter_table("dispatches") as batch:
        batch.add_column(sa.Column("original_vehicle_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("target_vehicle_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("transfer_node_id", sa.String(length=64), nullable=True))
        batch.create_foreign_key(
            "fk_dispatches_original_vehicle_id_fleet_vehicles",
            "fleet_vehicles",
            ["original_vehicle_id"],
            ["vehicle_id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_dispatches_target_vehicle_id_fleet_vehicles",
            "fleet_vehicles",
            ["target_vehicle_id"],
            ["vehicle_id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_dispatches_transfer_node_id_road_nodes",
            "road_nodes",
            ["transfer_node_id"],
            ["node_id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("dispatches") as batch:
        batch.drop_constraint("fk_dispatches_transfer_node_id_road_nodes", type_="foreignkey")
        batch.drop_constraint("fk_dispatches_target_vehicle_id_fleet_vehicles", type_="foreignkey")
        batch.drop_constraint("fk_dispatches_original_vehicle_id_fleet_vehicles", type_="foreignkey")
        batch.drop_column("transfer_node_id")
        batch.drop_column("target_vehicle_id")
        batch.drop_column("original_vehicle_id")
    with op.batch_alter_table("anomalies") as batch:
        batch.drop_constraint("fk_anomalies_affected_edge_id_road_edges", type_="foreignkey")
        batch.drop_constraint("fk_anomalies_incident_node_id_road_nodes", type_="foreignkey")
        batch.drop_column("affected_edge_id")
        batch.drop_column("incident_node_id")
    with op.batch_alter_table("orders") as batch:
        batch.drop_constraint("fk_orders_destination_station_id_logistics_stations", type_="foreignkey")
        batch.drop_constraint("fk_orders_origin_station_id_logistics_stations", type_="foreignkey")
        batch.drop_column("destination_station_id")
        batch.drop_column("origin_station_id")
        batch.drop_column("cargo_type")
        batch.drop_column("cargo_weight_kg")

    op.drop_index("ix_dispatch_evidence_dispatch_type", table_name="dispatch_evidence")
    op.drop_table("dispatch_evidence")
    op.drop_index("ix_road_edges_status_nodes", table_name="road_edges")
    op.drop_table("road_edges")
    op.drop_index("ix_fleet_vehicles_status_node", table_name="fleet_vehicles")
    op.drop_table("fleet_vehicles")
    op.drop_index("ix_road_nodes_status", table_name="road_nodes")
    op.drop_table("road_nodes")
    op.drop_index("ix_fleet_drivers_status_node", table_name="fleet_drivers")
    op.drop_table("fleet_drivers")
    op.drop_index("ix_logistics_stations_status_county", table_name="logistics_stations")
    op.drop_table("logistics_stations")
