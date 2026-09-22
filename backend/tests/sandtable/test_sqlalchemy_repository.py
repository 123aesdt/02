import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import URL, create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.fleet_driver import FleetDriver
from app.models.fleet_vehicle import FleetVehicle
from app.models.order import Order
from app.models.road import RoadEdge, RoadNode
from app.models.station import LogisticsStation
from app.road_network.sqlalchemy_repository import SqlAlchemyRoadNetworkRepository
from app.sandtable.seed_data import ORDERS
from app.sandtable.service import RoadLocationUnresolved, SandtableContextService
from app.sandtable.sqlalchemy_repository import (
    SandtableOrderConflictError,
    SqlAlchemySandtableRepository,
    seed_new_county_sandtable,
)
from app.seed import (
    DEMO_BUSINESS_CASES,
    DEMO_REPORT_SOURCE_TASKS,
    LegacyDemoOrderConflictError,
    seed_database,
)


def test_seed_is_idempotent_preserves_user_rows_and_loads_demo_context(sqlite_factory) -> None:
    with sqlite_factory() as session:
        seed_new_county_sandtable(session)
        session.commit()
        session.add(
            FleetVehicle(
                vehicle_id="USER-V-001",
                plate_no="用户车辆-01",
                vehicle_type="VAN",
                max_load_kg=Decimal("800.00"),
                current_load_kg=Decimal("0.00"),
                cargo_capability="GENERAL",
                gross_weight_tons=Decimal("1.50"),
                status="AVAILABLE",
                current_node_id="N01",
                assigned_driver_id=None,
            )
        )
        session.commit()
    with sqlite_factory() as session:
        seed_new_county_sandtable(session)
        session.commit()
    with sqlite_factory() as session:
        repository = SqlAlchemySandtableRepository(session)
        order_id = session.scalar(select(Order.id).where(Order.order_no == "DEMO-ORDER-001"))
        context = repository.load(order_id)
        assert (context.order_no, context.cargo_weight_kg, context.cargo_type) == ("DEMO-ORDER-001", Decimal("700.00"), "COLD_CHAIN")
        assert (context.origin_node_id, context.destination_node_id, context.current_vehicle_id, context.current_driver_id) == ("N01", "N06", "V-001", "D-001")
        assert session.scalar(select(func.count()).select_from(RoadEdge)) == 36
        assert session.scalar(select(func.count()).select_from(FleetVehicle)) == 21
        assert session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == "USER-V-001")) is not None


def test_seed_contains_every_operational_node_used_by_the_live_map(sqlite_factory) -> None:
    expected_node_ids = {"N19", "N20", "N21", "N22"}
    expected_station_names = {
        "智慧物流调度中心",
        "快递集散站",
        "新能源车辆充电站",
        "应急救援站",
    }

    with sqlite_factory() as session:
        seed_new_county_sandtable(session)
        session.commit()

        node_ids = set(
            session.scalars(select(RoadNode.node_id).where(RoadNode.node_id.in_(expected_node_ids))).all()
        )
        station_names = set(
            session.scalars(select(LogisticsStation.name).where(LogisticsStation.name.in_(expected_station_names))).all()
        )
        connected_node_ids = {
            node_id
            for edge in session.scalars(select(RoadEdge)).all()
            for node_id in (edge.from_node_id, edge.to_node_id)
            if node_id in expected_node_ids
        }

    assert node_ids == expected_node_ids
    assert station_names == expected_station_names
    assert connected_node_ids == expected_node_ids


def test_seed_upgrades_initial_live_map_link_travel_times_without_resetting_data(sqlite_factory) -> None:
    with sqlite_factory() as session:
        seed_new_county_sandtable(session)
        session.commit()
        session.scalar(select(RoadEdge).where(RoadEdge.edge_id == "E27")).base_minutes = 9
        session.scalar(select(RoadEdge).where(RoadEdge.edge_id == "E32")).base_minutes = 3
        session.scalar(select(RoadEdge).where(RoadEdge.edge_id == "E33")).base_minutes = 5
        session.scalar(select(RoadEdge).where(RoadEdge.edge_id == "E34")).base_minutes = 4
        session.commit()

    with sqlite_factory() as session:
        seed_new_county_sandtable(session)
        session.commit()
        upgraded = dict(
            session.execute(
                select(RoadEdge.edge_id, RoadEdge.base_minutes).where(
                    RoadEdge.edge_id.in_({"E27", "E32", "E33", "E34"})
                )
            ).all()
        )

    assert upgraded == {"E27": 15, "E32": 7, "E33": 9, "E34": 7}


def test_edge_status_only_increments_version_when_value_changes(sqlite_factory) -> None:
    with sqlite_factory() as session:
        seed_new_county_sandtable(session)
        session.commit()
    with sqlite_factory() as session:
        repository = SqlAlchemySandtableRepository(session)
        initial = session.scalar(select(RoadEdge).where(RoadEdge.edge_id == "E04")).version
        assert repository.set_edge_status("E04", "OPEN") == initial
        assert repository.set_edge_status("E04", "BLOCKED") == initial + 1
        assert repository.set_edge_status("E04", "BLOCKED") == initial + 1


def test_service_resolves_only_approved_aliases_and_blocks_named_edges(sqlite_factory) -> None:
    with sqlite_factory() as session:
        seed_new_county_sandtable(session)
        session.commit()
    with sqlite_factory() as session:
        repository = SqlAlchemySandtableRepository(session)
        service = SandtableContextService(repository)
        order_id = session.scalar(select(Order.id).where(Order.order_no == "DEMO-ORDER-001"))
        context = service.resolve(order_id, "VEHICLE_BREAKDOWN", "新物冷链-01 在新平路 K3.2 发生故障", None)
        assert (context.current_vehicle_id, context.incident_node_id, context.affected_edge_ids) == ("V-001", "N04", ())
        road_context = service.resolve(order_id, "ROAD_BLOCKED", "新平路东河桥段发生塌方", None)
        assert road_context.affected_edge_ids == ("E04",)
        assert session.scalar(select(RoadEdge.status).where(RoadEdge.edge_id == "E04")) == "BLOCKED"
        route_03_context = service.resolve(order_id, "ROAD_BLOCKED", "中心仓至 308 线发生塌方，车辆需要绕行。", None)
        assert route_03_context.affected_edge_ids == ("E10",)
        assert session.scalar(select(RoadEdge.status).where(RoadEdge.edge_id == "E10")) == "BLOCKED"
        with pytest.raises(RoadLocationUnresolved):
            service.resolve(order_id, "ROAD_BLOCKED", "新平路有道路问题", None)


def test_load_resolves_virtual_order_endpoints_by_unique_road_node_name(sqlite_factory) -> None:
    with sqlite_factory() as session:
        seed_new_county_sandtable(session)
        order = Order(
            order_no="DEMO-REPORT-ORDER-NAME-FALLBACK",
            status="IN_TRANSIT",
            driver_id="D-003",
            vehicle_id="V-005",
            route_id="ROUTE-03",
            origin="新平县中心仓",
            destination="北岭村驿站",
            cargo_weight_kg=Decimal("0.00"),
            cargo_type="GENERAL",
            origin_station_id=None,
            destination_station_id=None,
        )
        session.add(order)
        session.commit()

        context = SqlAlchemySandtableRepository(session).load(order.id)

    assert context.origin_node_id == "N01"
    assert context.destination_node_id == "N11"


def test_service_rejects_request_vehicle_that_differs_from_order_assignment(sqlite_factory) -> None:
    with sqlite_factory() as session:
        seed_new_county_sandtable(session)
        session.commit()
        service = SandtableContextService(SqlAlchemySandtableRepository(session))
        order_id = session.scalar(select(Order.id).where(Order.order_no == "DEMO-ORDER-005"))

        with pytest.raises(ValueError):
            service.resolve(order_id, "ROUTE_RISK", "正常配送车辆身份校验", "V-001")

        context = service.resolve(order_id, "ROUTE_RISK", "正常配送车辆身份校验", "V-008")
        assert (context.current_vehicle_id, context.current_driver_id, context.vehicle_weight_tons) == (
            "V-008",
            "D-007",
            Decimal("4.50"),
        )


def test_database_seed_keeps_sandtable_and_legacy_orders(sqlite_factory) -> None:
    seed_database(session_factory=sqlite_factory, runtime_profile="test")
    with sqlite_factory() as session:
        sandtable = session.scalars(select(Order).where(Order.order_no.like("DEMO-ORDER-%"))).all()
        legacy = session.scalars(select(Order).where(Order.order_no.like("LEGACY-DEMO-ORDER-%"))).all()
        assert len(sandtable) == 12
        assert len(legacy) == 10
        assert session.scalar(select(Order).where(Order.order_no == "DEMO-ORDER-001")).vehicle_id == "V-001"
        assert session.scalar(select(Order).where(Order.order_no == "LEGACY-DEMO-ORDER-001")).vehicle_id == "demo-vehicle-001"


def test_seed_never_backfills_existing_driver_or_changes_its_version(sqlite_factory) -> None:
    with sqlite_factory() as session:
        session.add(FleetDriver(driver_id="D-001", name="用户司机", license_class="C1", status="OFF_DUTY", current_vehicle_id=None, current_node_id="N01"))
        session.commit()
    with sqlite_factory() as session:
        seed_new_county_sandtable(session)
        session.commit()
        driver = session.scalar(select(FleetDriver).where(FleetDriver.driver_id == "D-001"))
        assert (driver.name, driver.current_vehicle_id, driver.version) == ("用户司机", None, 1)


def _insert_pre_upgrade_order(session, case, *, vehicle_id: str | None = None) -> None:
    session.add(
        Order(
            order_no=case["legacy_order_no"],
            status=case["status"],
            driver_id=case["driver_id"],
            vehicle_id=case["vehicle_id"] if vehicle_id is None else vehicle_id,
            route_id=case["route_id"],
            origin=case["origin"],
            destination=case["destination"],
        )
    )
    session.commit()


def test_database_seed_upgrades_matching_legacy_order_without_losing_sandtable(sqlite_factory) -> None:
    with sqlite_factory() as session:
        _insert_pre_upgrade_order(session, DEMO_BUSINESS_CASES[0])
    seed_database(session_factory=sqlite_factory, runtime_profile="test")
    with sqlite_factory() as session:
        assert session.scalar(select(Order).where(Order.order_no == "LEGACY-DEMO-ORDER-001")).vehicle_id == "demo-vehicle-001"
        assert session.scalar(select(Order).where(Order.order_no == "DEMO-ORDER-001")).vehicle_id == "V-001"


def test_database_seed_rejects_nonmatching_legacy_key_without_overwriting_user_order(sqlite_factory) -> None:
    with sqlite_factory() as session:
        _insert_pre_upgrade_order(session, DEMO_BUSINESS_CASES[0], vehicle_id="用户车辆")
    with pytest.raises(LegacyDemoOrderConflictError, match="指纹不匹配"):
        seed_database(session_factory=sqlite_factory, runtime_profile="test")
    with sqlite_factory() as session:
        order = session.scalar(select(Order).where(Order.order_no == "DEMO-ORDER-001"))
        assert (order.vehicle_id, order.origin_station_id) == ("用户车辆", None)


def _mysql_test_urls() -> tuple[URL, URL, str]:
    env_path = os.getenv("COUNTYFLOW_MYSQL_INTEGRATION_DOCKER_ENV")
    if not env_path or not Path(env_path).is_file():
        pytest.skip("未设置可用的 opt-in MySQL 环境文件")
    values = {}
    for line in Path(env_path).read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    if not values.get("MYSQL_ROOT_PASSWORD"):
        pytest.skip("opt-in MySQL 环境文件缺少所需配置")
    database = f"countyflow_task2_{uuid4().hex}"
    host, port = os.getenv("COUNTYFLOW_MYSQL_INTEGRATION_HOST", "127.0.0.1"), int(os.getenv("COUNTYFLOW_MYSQL_INTEGRATION_PORT", "3306"))
    admin = URL.create("mysql+pymysql", username="root", password=values["MYSQL_ROOT_PASSWORD"], host=host, port=port)
    target = URL.create("mysql+pymysql", username="root", password=values["MYSQL_ROOT_PASSWORD"], host=host, port=port, database=database)
    return admin, target, database


def test_mysql_opt_in_seed_upgrade_foreign_keys_and_versions() -> None:
    admin_url, database_url, database = _mysql_test_urls()
    if isinstance(admin_url, str) or "***" not in str(admin_url) or "***" not in repr(admin_url):
        raise AssertionError("<REDACTED_DATABASE_URL> 未脱敏")
    if isinstance(database_url, str) or "***" not in str(database_url) or "***" not in repr(database_url):
        raise AssertionError("<REDACTED_DATABASE_URL> 未脱敏")
    admin = create_engine(admin_url, future=True)
    engine = None
    try:
        with admin.begin() as connection:
            connection.execute(text(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4"))
        engine = create_engine(database_url, future=True)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        seed_database(session_factory=factory, runtime_profile="test")
        seed_database(session_factory=factory, runtime_profile="test")
        with factory() as session:
            expected_order_count = (
                len(ORDERS)
                + len(DEMO_BUSINESS_CASES)
                + len(DEMO_REPORT_SOURCE_TASKS)
                + 1  # ORDER-E2E-RAIN-001
            )
            assert session.scalar(select(func.count()).select_from(Order)) == expected_order_count
            driver = session.scalar(select(FleetDriver).where(FleetDriver.driver_id == "D-001"))
            vehicle = session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == "V-001"))
            assert (driver.current_vehicle_id, vehicle.assigned_driver_id) == ("V-001", "D-001")
            repository = SqlAlchemySandtableRepository(session)
            version = session.scalar(select(RoadEdge.version).where(RoadEdge.edge_id == "E04"))
            assert repository.set_edge_status("E04", "OPEN") == version
            assert repository.set_edge_status("E04", "BLOCKED") == version + 1
    finally:
        if engine is not None:
            engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS `{database}`"))
        admin.dispose()


def test_seed_conflict_rolls_back_all_new_sandtable_rows_after_caller_commit(sqlite_factory) -> None:
    with sqlite_factory() as session:
        session.add(
            Order(
                order_no="DEMO-ORDER-001",
                status="USER",
                driver_id="user-driver",
                vehicle_id="user-vehicle",
                route_id="user-route",
                origin="用户起点",
                destination="用户终点",
            )
        )
        session.commit()
        with pytest.raises(SandtableOrderConflictError, match="指纹不匹配"):
            seed_new_county_sandtable(session)
        session.commit()
    with sqlite_factory() as session:
        user_order = session.scalar(select(Order).where(Order.order_no == "DEMO-ORDER-001"))
        assert (user_order.status, user_order.vehicle_id, user_order.origin) == ("USER", "user-vehicle", "用户起点")
        assert session.scalar(select(func.count()).select_from(RoadNode)) == 0
        assert session.scalar(select(func.count()).select_from(LogisticsStation)) == 0
        assert session.scalar(select(func.count()).select_from(RoadEdge)) == 0
        assert session.scalar(select(func.count()).select_from(FleetVehicle)) == 0
        assert session.scalar(select(func.count()).select_from(FleetDriver)) == 0
        assert session.scalar(select(func.count()).select_from(Order)) == 1


def test_seed_savepoint_rolls_back_partial_flush_and_keeps_outer_transaction(sqlite_factory, monkeypatch) -> None:
    with sqlite_factory() as session:
        session.add(
            Order(order_no="OUTER-ORDER-001", status="OUTER", driver_id=None, vehicle_id=None, route_id=None, origin="外层起点", destination="外层终点")
        )
        session.flush()
        original_flush = session.flush
        observed_nodes_before_failure = 0

        def fail_after_nodes(*args, **kwargs):
            nonlocal observed_nodes_before_failure
            result = original_flush(*args, **kwargs)
            with session.no_autoflush:
                node_count = session.scalar(select(func.count()).select_from(RoadNode))
            if node_count == 18:
                observed_nodes_before_failure = node_count
                raise RuntimeError("测试注入的节点 flush 后失败")
            return result

        monkeypatch.setattr(session, "flush", fail_after_nodes)
        with pytest.raises(RuntimeError, match="节点 flush 后"):
            seed_new_county_sandtable(session)
        assert observed_nodes_before_failure == 18
        monkeypatch.setattr(session, "flush", original_flush)
        session.commit()
    with sqlite_factory() as session:
        assert session.scalar(select(Order.status).where(Order.order_no == "OUTER-ORDER-001")) == "OUTER"
        assert session.scalar(select(func.count()).select_from(RoadNode)) == 0
        assert session.scalar(select(func.count()).select_from(LogisticsStation)) == 0
        assert session.scalar(select(func.count()).select_from(FleetDriver)) == 0
        assert session.scalar(select(func.count()).select_from(FleetVehicle)) == 0
        assert session.scalar(select(func.count()).select_from(RoadEdge)) == 0
        assert session.scalar(select(func.count()).select_from(Order)) == 1

def test_road_repository_factory_reads_latest_committed_snapshot(sqlite_factory) -> None:
    with sqlite_factory() as session:
        seed_new_county_sandtable(session)
        session.commit()
    repository = SqlAlchemyRoadNetworkRepository(sqlite_factory)
    first = repository.snapshot()
    with sqlite_factory() as session:
        edge = session.scalar(select(RoadEdge).where(RoadEdge.edge_id == "E04"))
        edge.status = "BLOCKED"
        session.commit()
    second = repository.snapshot()
    assert next(edge for edge in first.edges if edge.edge_id == "E04").status == "OPEN"
    blocked = next(edge for edge in second.edges if edge.edge_id == "E04")
    assert blocked.status == "BLOCKED"
    assert second.version > first.version
