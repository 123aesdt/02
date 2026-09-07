from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event, Lock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

import app.dispatch.service as dispatch_service_module
from app.dispatch.service import DispatchService
from app.models.base import Base
from app.models.dispatch import Dispatch
from app.models.dispatch_evidence import DispatchEvidence
from app.models.fleet_driver import FleetDriver
from app.models.fleet_vehicle import FleetVehicle
from app.models.order import Order
from app.models.road import RoadNode
from app.models.task import DispatchTask


class ReservationSession(Session):
    pass


def _candidate(vehicle_id: str, driver_id: str, score: str) -> dict[str, object]:
    return {
        "vehicle_id": vehicle_id,
        "driver_id": driver_id,
        "eligible": True,
        "vehicle_status": "AVAILABLE",
        "remaining_load_kg": "900.00",
        "cargo_capability": "COLD_CHAIN",
        "score": score,
        "exclusion_reasons": [],
    }


def _execution_args(
    task_id: str,
    order_id: int,
    candidates: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "task_id": task_id,
        "order_id": order_id,
        "original_route_id": "RTE-ORIGINAL",
        "target_route_id": "RTE-TARGET",
        "decision": "REROUTE",
        "decision_reason": "替代车辆与路线均满足约束。",
        "fallback_used": False,
        "fallback_reason": None,
        "requires_manual_review": False,
        "original_vehicle_id": "V-001",
        "candidate_vehicles": candidates,
        "transfer_node_id": "N04",
        "fleet_evidence": {"algorithm_version": "FLEET_SCORE_V1", "candidates": candidates},
        "route_evidence": {
            "algorithm_version": "DIJKSTRA_V1",
            "road_network_version": 7,
            "recommended_path": {
                "node_ids": ["N04", "N06"],
                "edge_ids": ["E04", "E05"],
            },
        },
    }


def _seed(factory: sessionmaker[Session], *, vehicle_count: int = 2) -> tuple[int, int]:
    with factory() as session:
        session.add_all(
            [
                RoadNode(node_id="N04", name="故障点", x_km=5, y_km=2, node_type="INCIDENT_POINT"),
                RoadNode(node_id="N15", name="维修站", x_km=4, y_km=1, node_type="STATION"),
            ]
        )
        session.flush()
        drivers = [
            FleetDriver(
                driver_id=f"D-{suffix - 2:03d}",
                name=f"司机{suffix}",
                license_class="C1",
                status="ON_DUTY",
                current_vehicle_id=None,
                current_node_id="N15",
            )
            for suffix in range(5, 5 + vehicle_count)
        ]
        session.add_all(drivers)
        session.flush()
        session.add_all(
            [
                FleetVehicle(
                    vehicle_id=f"V-{suffix:03d}",
                    plate_no=f"新物冷链-{suffix:02d}",
                    vehicle_type="REFRIGERATED_VAN",
                    max_load_kg=1000,
                    current_load_kg=100,
                    cargo_capability="COLD_CHAIN",
                    gross_weight_tons="2.40",
                    status="AVAILABLE",
                    current_node_id="N15",
                    assigned_driver_id=f"D-{suffix - 2:03d}",
                )
                for suffix in range(5, 5 + vehicle_count)
            ]
        )
        session.flush()
        for suffix, driver in zip(range(5, 5 + vehicle_count), drivers, strict=True):
            driver.current_vehicle_id = f"V-{suffix:03d}"
        orders = [
            Order(order_no="ORD-RACE-A", status="open", origin="A", destination="B"),
            Order(order_no="ORD-RACE-B", status="open", origin="A", destination="B"),
        ]
        session.add_all(orders)
        session.flush()
        session.add_all(
            [
                DispatchTask(
                    task_id="task-race-a",
                    order_id=orders[0].id,
                    status="created",
                    idempotency_key="race-a",
                ),
                DispatchTask(
                    task_id="task-race-b",
                    order_id=orders[1].id,
                    status="created",
                    idempotency_key="race-b",
                ),
            ]
        )
        session.commit()
        return orders[0].id, orders[1].id


def _install_first_reservation_barrier(factory: sessionmaker[Session]) -> None:
    rendezvous = Barrier(2)
    winner_committed = Event()
    arrival_lock = Lock()
    arrivals = 0

    @event.listens_for(factory.class_, "loaded_as_persistent")
    def synchronize_first_vehicle_load(session: Session, row: object) -> None:
        nonlocal arrivals
        if (
            not isinstance(row, FleetVehicle)
            or row.vehicle_id != "V-005"
            or session.info.get("reservation_barrier_passed")
        ):
            return
        with arrival_lock:
            if arrivals >= 2:
                return
            session.info["reservation_barrier_passed"] = True
            arrival_index = arrivals
            arrivals += 1
        rendezvous.wait(timeout=10)
        if arrival_index == 1 and not winner_committed.wait(timeout=10):
            raise TimeoutError("首个车辆预占未在并发测试时限内提交")

    @event.listens_for(factory.class_, "after_commit")
    def release_loser(session: Session) -> None:
        if session.info.get("reservation_barrier_passed"):
            winner_committed.set()

def _run_race(
    factory: sessionmaker[Session],
    order_ids: tuple[int, int],
    candidates: list[dict[str, object]],
) -> list[object]:
    service = DispatchService(factory)

    def execute(task_id: str, order_id: int) -> object:
        try:
            return service.execute(**_execution_args(task_id, order_id, candidates))
        except Exception as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(execute, "task-race-a", order_ids[0]),
            executor.submit(execute, "task-race-b", order_ids[1]),
        ]
        return [future.result(timeout=20) for future in futures]


def _factory(path: Path) -> tuple[object, sessionmaker[Session]]:
    class TestReservationSession(ReservationSession):
        pass

    engine = create_engine(
        f"sqlite+pysqlite:///{path}",
        connect_args={"timeout": 10},
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(
        bind=engine,
        class_=TestReservationSession,
        expire_on_commit=False,
    )

def test_two_sessions_reserve_distinct_ranked_vehicles_and_persist_two_evidence_rows() -> None:
    with TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        engine, factory = _factory(Path(temp_dir) / "vehicle-race.db")
        try:
            order_ids = _seed(factory)
            _install_first_reservation_barrier(factory)
            candidates = [
                _candidate("V-005", "D-003", "93.4"),
                _candidate("V-006", "D-004", "90.0"),
            ]

            results = _run_race(factory, order_ids, candidates)

            assert all(not isinstance(result, Exception) for result in results), [repr(result) for result in results]
            with factory() as session:
                dispatches = list(session.scalars(select(Dispatch).order_by(Dispatch.id)))
                vehicles = list(
                    session.scalars(select(FleetVehicle).order_by(FleetVehicle.vehicle_id))
                )
                evidence_counts = {
                    dispatch.id: session.scalar(
                        select(func.count())
                        .select_from(DispatchEvidence)
                        .where(DispatchEvidence.dispatch_id == dispatch.id)
                    )
                    for dispatch in dispatches
                }
            assert {dispatch.target_vehicle_id for dispatch in dispatches} == {
                "V-005",
                "V-006",
            }
            assert {dispatch.target_driver_id for dispatch in dispatches} == {
                "D-003",
                "D-004",
            }
            assert [(vehicle.vehicle_id, vehicle.status) for vehicle in vehicles] == [
                ("V-005", "RESERVED"),
                ("V-006", "RESERVED"),
            ]
            assert evidence_counts == {dispatch.id: 2 for dispatch in dispatches}
        finally:
            engine.dispose()

def test_two_sessions_with_one_candidate_return_one_reservation_conflict() -> None:
    with TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        engine, factory = _factory(Path(temp_dir) / "vehicle-conflict.db")
        try:
            order_ids = _seed(factory, vehicle_count=1)
            _install_first_reservation_barrier(factory)

            results = _run_race(
                factory,
                order_ids,
                [_candidate("V-005", "D-003", "93.4")],
            )

            assert sum(not isinstance(result, Exception) for result in results) == 1
            conflict_type = dispatch_service_module.VehicleReservationConflict
            conflicts = [result for result in results if isinstance(result, conflict_type)]
            assert len(conflicts) == 1
            assert conflicts[0].code == "VEHICLE_RESERVATION_CONFLICT"
            with factory() as session:
                assert session.scalar(select(func.count()).select_from(Dispatch)) == 1
                assert session.scalar(select(func.count()).select_from(DispatchEvidence)) == 2
        finally:
            engine.dispose()

def _mysql_urls() -> tuple[URL, URL, str]:
    env_path = os.getenv("COUNTYFLOW_MYSQL_INTEGRATION_DOCKER_ENV")
    if not env_path or not Path(env_path).is_file():
        pytest.skip("未设置可用的 opt-in MySQL 环境文件")
    values: dict[str, str] = {}
    for line in Path(env_path).read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    if not values.get("MYSQL_ROOT_PASSWORD"):
        pytest.skip("opt-in MySQL 环境文件缺少所需配置")
    database = f"countyflow_task6_{uuid4().hex}"
    host = os.getenv("COUNTYFLOW_MYSQL_INTEGRATION_HOST", "127.0.0.1")
    port = int(os.getenv("COUNTYFLOW_MYSQL_INTEGRATION_PORT", "3306"))
    admin = URL.create(
        "mysql+pymysql",
        username="root",
        password=values["MYSQL_ROOT_PASSWORD"],
        host=host,
        port=port,
    )
    target = URL.create(
        "mysql+pymysql",
        username="root",
        password=values["MYSQL_ROOT_PASSWORD"],
        host=host,
        port=port,
        database=database,
    )
    return admin, target, database


def test_mysql_opt_in_two_sessions_reserve_distinct_ranked_vehicles() -> None:
    admin_url, database_url, database = _mysql_urls()
    assert "***" in str(admin_url) and "***" in str(database_url)
    admin = create_engine(admin_url, future=True)
    engine = None
    try:
        with admin.begin() as connection:
            connection.execute(
                text(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4")
            )
        engine = create_engine(database_url, future=True)
        Base.metadata.create_all(engine)

        class MySqlReservationSession(ReservationSession):
            pass

        factory = sessionmaker(
            bind=engine,
            class_=MySqlReservationSession,
            expire_on_commit=False,
        )
        order_ids = _seed(factory)
        _install_first_reservation_barrier(factory)
        results = _run_race(
            factory,
            order_ids,
            [
                _candidate("V-005", "D-003", "93.4"),
                _candidate("V-006", "D-004", "90.0"),
            ],
        )

        assert all(not isinstance(result, Exception) for result in results), [
            repr(result) for result in results
        ]
        with factory() as session:
            assert set(session.scalars(select(Dispatch.target_vehicle_id))) == {
                "V-005",
                "V-006",
            }
            assert session.scalar(select(func.count()).select_from(DispatchEvidence)) == 4
    finally:
        if engine is not None:
            engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS `{database}`"))
        admin.dispose()
