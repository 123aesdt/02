from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.fleet_vehicle import FleetVehicle
from app.models.order import Order
from app.models.road import RoadEdge
from app.sandtable.service import RoadLocationUnresolved, SandtableContextService
from app.sandtable.sqlalchemy_repository import SqlAlchemySandtableRepository, seed_new_county_sandtable


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
        assert session.scalar(select(func.count()).select_from(RoadEdge)) == 26
        assert session.scalar(select(func.count()).select_from(FleetVehicle)) == 13
        assert session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == "USER-V-001")) is not None


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


def test_service_resolves_only_approved_aliases_and_blocks_e04(sqlite_factory) -> None:
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
        with pytest.raises(RoadLocationUnresolved):
            service.resolve(order_id, "ROAD_BLOCKED", "新平路有道路问题", None)
