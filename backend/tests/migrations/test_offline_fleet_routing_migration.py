import os
import re
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, select
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from app.models.dispatch import Dispatch
from app.models.dispatch_evidence import DispatchEvidence
from app.models.fleet_driver import FleetDriver
from app.models.fleet_vehicle import FleetVehicle
from app.models.order import Order
from app.models.road import RoadEdge, RoadNode
from app.models.station import LogisticsStation


def _load_migration_module():
    path = Path(__file__).parents[2] / "alembic" / "versions" / "20260902_13_offline_fleet_routing.py"
    spec = spec_from_file_location("offline_fleet_routing", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_offline_fleet_models_match_approved_sandbox_schema() -> None:
    assert {"cargo_weight_kg", "cargo_type", "origin_station_id", "destination_station_id"} <= set(Order.__table__.columns.keys())
    assert {"original_vehicle_id", "target_vehicle_id", "transfer_node_id"} <= set(Dispatch.__table__.columns.keys())
    assert FleetDriver.__mapper__.version_id_col is FleetDriver.__table__.c.version
    assert FleetVehicle.__mapper__.version_id_col is FleetVehicle.__table__.c.version
    assert RoadEdge.__mapper__.version_id_col is RoadEdge.__table__.c.version

    station_columns = LogisticsStation.__table__.c
    assert {"id", "station_id", "name", "station_type", "road_node_id", "handling_capacity_kg", "status"} <= set(station_columns.keys())
    assert station_columns.handling_capacity_kg.type.precision == 12
    assert station_columns.handling_capacity_kg.type.scale == 2
    assert not station_columns.road_node_id.nullable

    driver_columns = FleetDriver.__table__.c
    assert {"id", "driver_id", "name", "license_class", "status", "current_vehicle_id", "current_node_id", "version"} <= set(driver_columns.keys())
    assert driver_columns.license_class.type.length == 16
    assert driver_columns.current_vehicle_id.nullable
    assert not driver_columns.current_node_id.nullable

    node_columns = RoadNode.__table__.c
    assert set(node_columns.keys()) == {"id", "node_id", "name", "x_km", "y_km", "node_type", "created_at", "updated_at"}
    assert node_columns.x_km.type.precision == 8
    assert node_columns.x_km.type.scale == 2

    edge_columns = RoadEdge.__table__.c
    assert {
        "id",
        "edge_id",
        "name",
        "from_node_id",
        "to_node_id",
        "distance_km",
        "base_minutes",
        "road_level",
        "risk_level",
        "status",
        "congestion_factor",
        "weight_limit_tons",
        "bidirectional",
        "version",
    } | {"created_at", "updated_at"} == set(edge_columns.keys())
    assert edge_columns.distance_km.type.precision == 8
    assert edge_columns.distance_km.type.scale == 2
    assert edge_columns.congestion_factor.type.precision == 5
    assert edge_columns.congestion_factor.type.scale == 2
    assert edge_columns.weight_limit_tons.type.precision == 6
    assert edge_columns.weight_limit_tons.type.scale == 2
    assert edge_columns.congestion_factor.default.arg == Decimal("1.00")

    evidence_columns = DispatchEvidence.__table__.c
    assert {"id", "dispatch_id", "evidence_type", "algorithm_version", "payload_json", "road_network_version"} <= set(evidence_columns.keys())
    assert evidence_columns.evidence_type.type.length == 32
    assert evidence_columns.algorithm_version.type.length == 32
    assert evidence_columns.payload_json.type.__class__.__name__ == "JSON"
    assert evidence_columns.road_network_version.nullable
    assert next(iter(evidence_columns.dispatch_id.foreign_keys)).ondelete == "CASCADE"


def test_offline_fleet_migration_continues_from_current_head() -> None:
    module = _load_migration_module()
    assert module.revision == "20260902_13"
    assert module.down_revision == "20260901_12"


def test_offline_fleet_migration_upgrades_and_downgrades_legacy_rows() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    orders = Table(
        "orders",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("order_no", String(64), nullable=False),
        Column("status", String(32), nullable=False),
        Column("origin", String(255), nullable=False),
        Column("destination", String(255), nullable=False),
    )
    anomalies = Table(
        "anomalies",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("anomaly_no", String(64), nullable=False),
        Column("status", String(32), nullable=False),
    )
    dispatches = Table(
        "dispatches",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("dispatch_no", String(64), nullable=False),
        Column("status", String(32), nullable=False),
        Column("version", Integer, nullable=False),
    )
    metadata.create_all(engine)

    module = _load_migration_module()
    with engine.begin() as connection:
        connection.execute(orders.insert().values(id=1, order_no="ORD-LEGACY", status="OPEN", origin="A", destination="B"))
        connection.execute(anomalies.insert().values(id=1, anomaly_no="ANM-LEGACY", status="OPEN"))
        connection.execute(dispatches.insert().values(id=1, dispatch_no="DSP-LEGACY", status="OPEN", version=1))

        original_op = module.op
        module.op = Operations(MigrationContext.configure(connection))
        try:
            module.upgrade()
            inspector = inspect(connection)
            station_columns = {column["name"]: column for column in inspector.get_columns("logistics_stations")}
            driver_columns = {column["name"]: column for column in inspector.get_columns("fleet_drivers")}
            edge_columns = {column["name"]: column for column in inspector.get_columns("road_edges")}
            evidence_columns = {column["name"]: column for column in inspector.get_columns("dispatch_evidence")}
            order_columns = {column["name"]: column for column in inspector.get_columns("orders")}

            assert station_columns["handling_capacity_kg"]["type"].precision == 12
            assert station_columns["handling_capacity_kg"]["type"].scale == 2
            assert not station_columns["road_node_id"]["nullable"]
            assert driver_columns["current_vehicle_id"]["nullable"]
            assert not driver_columns["current_node_id"]["nullable"]
            assert edge_columns["distance_km"]["type"].precision == 8
            assert edge_columns["distance_km"]["type"].scale == 2
            assert edge_columns["base_minutes"]["type"].__class__.__name__.upper() == "INTEGER"
            assert evidence_columns["payload_json"]["type"].__class__.__name__ == "JSON"
            assert order_columns["cargo_weight_kg"]["nullable"]
            assert connection.execute(select(orders.c.id)).scalar_one() == 1
            assert connection.exec_driver_sql(
                "SELECT cargo_weight_kg, cargo_type, origin_station_id, destination_station_id FROM orders WHERE id = 1"
            ).one() == (None, None, None, None)
            assert any(foreign_key["options"].get("ondelete") == "CASCADE" for foreign_key in inspector.get_foreign_keys("dispatch_evidence"))
            assert edge_columns["congestion_factor"]["default"].strip("'") == "1.00"
            assert {constraint["name"] for constraint in inspector.get_unique_constraints("logistics_stations")} >= {"uq_logistics_stations_station_id"}
            assert {constraint["name"] for constraint in inspector.get_unique_constraints("fleet_drivers")} >= {"uq_fleet_drivers_driver_id"}
            assert {constraint["name"] for constraint in inspector.get_unique_constraints("fleet_vehicles")} >= {
                "uq_fleet_vehicles_vehicle_id",
                "uq_fleet_vehicles_plate_no",
            }
            for table_name in ("logistics_stations", "fleet_drivers", "fleet_vehicles", "road_edges"):
                assert inspector.get_foreign_keys(table_name)
                assert all(foreign_key["options"].get("ondelete") == "RESTRICT" for foreign_key in inspector.get_foreign_keys(table_name))

            module.downgrade()
            downgraded = inspect(connection)
            assert "logistics_stations" not in downgraded.get_table_names()
            assert "cargo_weight_kg" not in {column["name"] for column in downgraded.get_columns("orders")}
            assert connection.execute(select(orders.c.id)).scalar_one() == 1
        finally:
            module.op = original_op


def _mysql_integration_urls() -> tuple[str, str, str]:
    docker_env_path = os.getenv("COUNTYFLOW_MYSQL_INTEGRATION_DOCKER_ENV")
    if not docker_env_path:
        pytest.skip("未设置 COUNTYFLOW_MYSQL_INTEGRATION_DOCKER_ENV，跳过 opt-in MySQL 迁移集成测试")

    path = Path(docker_env_path)
    if not path.is_file():
        pytest.skip("opt-in MySQL 环境文件不可用，跳过集成测试")

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", maxsplit=1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    required = ("MYSQL_ROOT_PASSWORD",)
    if any(not values.get(key) for key in required):
        pytest.skip("opt-in MySQL 环境文件缺少集成测试所需配置")

    host = os.getenv("COUNTYFLOW_MYSQL_INTEGRATION_HOST", "127.0.0.1")
    port = int(os.getenv("COUNTYFLOW_MYSQL_INTEGRATION_PORT", "3306"))
    temporary_database = f"countyflow_task1_{uuid4().hex}"
    assert re.fullmatch(r"countyflow_task1_[0-9a-f]{32}", temporary_database)
    admin_url = URL.create(
        "mysql+pymysql",
        username="root",
        password=values["MYSQL_ROOT_PASSWORD"],
        host=host,
        port=port,
    ).render_as_string(hide_password=False)
    database_url = URL.create(
        "mysql+pymysql",
        username="root",
        password=values["MYSQL_ROOT_PASSWORD"],
        host=host,
        port=port,
        database=temporary_database,
    ).render_as_string(hide_password=False)
    return admin_url, database_url, temporary_database


def test_offline_fleet_migration_mysql_round_trip() -> None:
    admin_url, database_url, temporary_database = _mysql_integration_urls()
    admin_engine = sa.create_engine(admin_url, future=True)
    database_engine = None
    module = _load_migration_module()
    try:
        with admin_engine.begin() as connection:
            connection.execute(sa.text(f"CREATE DATABASE `{temporary_database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
        database_engine = sa.create_engine(database_url, future=True)
        legacy_metadata = MetaData()
        orders = Table(
            "orders",
            legacy_metadata,
            Column("id", Integer, primary_key=True),
            Column("order_no", String(64), nullable=False),
            Column("status", String(32), nullable=False),
            Column("origin", String(255), nullable=False),
            Column("destination", String(255), nullable=False),
        )
        anomalies = Table(
            "anomalies",
            legacy_metadata,
            Column("id", Integer, primary_key=True),
            Column("anomaly_no", String(64), nullable=False),
            Column("status", String(32), nullable=False),
        )
        dispatches = Table(
            "dispatches",
            legacy_metadata,
            Column("id", Integer, primary_key=True),
            Column("dispatch_no", String(64), nullable=False),
            Column("status", String(32), nullable=False),
            Column("version", Integer, nullable=False),
        )
        with database_engine.begin() as connection:
            legacy_metadata.create_all(connection)
            connection.execute(orders.insert().values(id=1, order_no="ORD-MYSQL-LEGACY", status="OPEN", origin="A", destination="B"))
            connection.execute(anomalies.insert().values(id=1, anomaly_no="ANM-MYSQL-LEGACY", status="OPEN"))
            connection.execute(dispatches.insert().values(id=1, dispatch_no="DSP-MYSQL-LEGACY", status="OPEN", version=1))

            original_op = module.op
            module.op = Operations(MigrationContext.configure(connection))
            try:
                module.upgrade()
                metadata = MetaData()
                road_nodes = Table("road_nodes", metadata, autoload_with=connection)
                stations = Table("logistics_stations", metadata, autoload_with=connection)
                drivers = Table("fleet_drivers", metadata, autoload_with=connection)
                vehicles = Table("fleet_vehicles", metadata, autoload_with=connection)
                edges = Table("road_edges", metadata, autoload_with=connection)
                evidence = Table("dispatch_evidence", metadata, autoload_with=connection)
                upgraded_dispatches = Table("dispatches", metadata, autoload_with=connection)

                connection.execute(
                    road_nodes.insert().values(
                        node_id="N-MYSQL-1",
                        name="MySQL 集成节点",
                        x_km=Decimal("1.25"),
                        y_km=Decimal("2.50"),
                        node_type="STATION",
                        created_at=sa.func.now(),
                        updated_at=sa.func.now(),
                    )
                )
                connection.execute(
                    stations.insert().values(
                        station_id="ST-MYSQL-1",
                        name="MySQL 集成站点",
                        station_type="HUB",
                        road_node_id="N-MYSQL-1",
                        handling_capacity_kg=Decimal("1234.50"),
                        status="ACTIVE",
                        created_at=sa.func.now(),
                        updated_at=sa.func.now(),
                    )
                )
                connection.execute(
                    drivers.insert().values(
                        driver_id="D-MYSQL-1",
                        name="MySQL 集成司机",
                        license_class="C1",
                        status="ON_DUTY",
                        current_vehicle_id=None,
                        current_node_id="N-MYSQL-1",
                        version=1,
                        created_at=sa.func.now(),
                        updated_at=sa.func.now(),
                    )
                )
                connection.execute(
                    vehicles.insert().values(
                        vehicle_id="V-MYSQL-1",
                        plate_no="MYSQL-001",
                        vehicle_type="VAN",
                        max_load_kg=Decimal("1500.00"),
                        current_load_kg=Decimal("100.00"),
                        cargo_capability="GENERAL",
                        gross_weight_tons=Decimal("2.50"),
                        status="AVAILABLE",
                        current_node_id="N-MYSQL-1",
                        assigned_driver_id="D-MYSQL-1",
                        version=1,
                        created_at=sa.func.now(),
                        updated_at=sa.func.now(),
                    )
                )
                connection.execute(drivers.update().where(drivers.c.driver_id == "D-MYSQL-1").values(current_vehicle_id="V-MYSQL-1"))
                connection.execute(
                    edges.insert().values(
                        edge_id="E-MYSQL-1",
                        name="MySQL 集成道路",
                        from_node_id="N-MYSQL-1",
                        to_node_id="N-MYSQL-1",
                        distance_km=Decimal("3.75"),
                        base_minutes=7,
                        road_level="COUNTY",
                        risk_level="LOW",
                        status="OPEN",
                        congestion_factor=Decimal("1.25"),
                        weight_limit_tons=Decimal("8.50"),
                        bidirectional=True,
                        version=1,
                        created_at=sa.func.now(),
                        updated_at=sa.func.now(),
                    )
                )
                connection.execute(
                    upgraded_dispatches.insert().values(
                        id=2,
                        dispatch_no="DSP-MYSQL-EVIDENCE",
                        status="OPEN",
                        version=1,
                    )
                )
                connection.execute(
                    evidence.insert().values(
                        dispatch_id=2,
                        evidence_type="ROUTE_CALCULATION",
                        algorithm_version="DIJKSTRA_V1",
                        payload_json={"edge_ids": ["E-MYSQL-1"], "score": "93.4"},
                        road_network_version=3,
                        created_at=sa.func.now(),
                        updated_at=sa.func.now(),
                    )
                )

                station_row = connection.execute(sa.select(stations.c.handling_capacity_kg).where(stations.c.station_id == "ST-MYSQL-1")).scalar_one()
                evidence_row = connection.execute(sa.select(evidence.c.payload_json, evidence.c.road_network_version).where(evidence.c.dispatch_id == 2)).one()
                assert station_row == Decimal("1234.50")
                assert evidence_row == ({"edge_ids": ["E-MYSQL-1"], "score": "93.4"}, 3)
                with pytest.raises(IntegrityError):
                    connection.execute(
                        vehicles.insert().values(
                            vehicle_id="V-MYSQL-1",
                            plate_no="MYSQL-002",
                            vehicle_type="VAN",
                            max_load_kg=Decimal("1.00"),
                            current_load_kg=Decimal("0.00"),
                            cargo_capability="GENERAL",
                            gross_weight_tons=Decimal("1.00"),
                            status="AVAILABLE",
                            current_node_id="N-MYSQL-1",
                            assigned_driver_id=None,
                            version=1,
                            created_at=sa.func.now(),
                            updated_at=sa.func.now(),
                        )
                    )
                with pytest.raises(IntegrityError):
                    connection.execute(road_nodes.delete().where(road_nodes.c.node_id == "N-MYSQL-1"))
                connection.execute(upgraded_dispatches.delete().where(upgraded_dispatches.c.id == 2))
                assert connection.execute(sa.select(sa.func.count()).select_from(evidence)).scalar_one() == 0
                assert connection.execute(sa.select(upgraded_dispatches.c.id).where(upgraded_dispatches.c.id == 1)).scalar_one() == 1

                module.downgrade()
                inspector = inspect(connection)
                assert "road_nodes" not in inspector.get_table_names()
                assert "cargo_weight_kg" not in {column["name"] for column in inspector.get_columns("orders")}
                assert connection.execute(sa.select(orders.c.id)).scalar_one() == 1
            finally:
                module.op = original_op
    finally:
        if database_engine is not None:
            database_engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(sa.text(f"DROP DATABASE IF EXISTS `{temporary_database}`"))
        admin_engine.dispose()
