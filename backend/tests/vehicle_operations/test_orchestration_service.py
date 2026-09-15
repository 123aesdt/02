from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.models.fleet_vehicle import FleetVehicle
from app.models.order import Order
from app.models.task import DispatchTask
from app.models.vehicle_operation import MaintenanceBay, RescueUnit
from app.road_network.dijkstra import DijkstraPathFinder
from app.road_network.sqlalchemy_repository import SqlAlchemyRoadNetworkRepository
from app.sandtable.sqlalchemy_repository import seed_new_county_sandtable
from app.vehicle_operations.models import BreakdownCaseRequest
from app.vehicle_operations.service import BreakdownOrchestrationInput, RescueOrchestrationService
from app.vehicle_operations.sqlalchemy_repository import SqlAlchemyVehicleOperationsRepository

NOW = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)


class FixedClock:
    def now(self):
        return NOW


def _seed(factory):
    with factory() as session:
        seed_new_county_sandtable(session)
        order = session.scalar(select(Order).where(Order.order_no == "DEMO-ORDER-001"))
        assert order is not None
        session.add(DispatchTask(task_id="TASK-ORCH-001", order_id=order.id, status="APPROVED", idempotency_key="orch-1"))
        session.add(
            RescueUnit(
                unit_id="RU-001",
                name="县域道路救援-02",
                plate_no="新救援-02",
                unit_type="TOW_TRUCK",
                status="AVAILABLE",
                current_node_id="N15",
                capacity_tons="5.00",
            )
        )
        session.add(MaintenanceBay(bay_code="A-02", station_id="ST-007", status="AVAILABLE"))
        session.commit()


def test_orchestration_uses_persisted_topology_and_creates_complete_case(sqlite_factory):
    _seed(sqlite_factory)
    with sqlite_factory() as session:
        replacement = session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == "V-005"))
        assert replacement is not None
        replacement.current_node_id = "N01"
        session.commit()
    service = RescueOrchestrationService(
        SqlAlchemyVehicleOperationsRepository(sqlite_factory),
        SqlAlchemyRoadNetworkRepository(sqlite_factory),
        DijkstraPathFinder(),
        FixedClock(),
    )

    case = service.orchestrate(
        BreakdownOrchestrationInput(
            task_id="TASK-ORCH-001",
            vehicle_id="V-001",
            replacement_vehicle_id="V-005",
            incident_node_id="N04",
            cargo_type="COLD_CHAIN",
            severity="HIGH",
            fault_code="ENGINE_COOLING",
        )
    )

    snapshot = SqlAlchemyRoadNetworkRepository(sqlite_factory).snapshot()
    edge_ids = {edge.edge_id for edge in snapshot.edges}
    assert set(case.mission.outbound_edge_ids) <= edge_ids
    assert set(case.mission.tow_edge_ids) <= edge_ids
    assert case.mission.outbound_edge_ids == ("E20",)
    assert case.replacement_edge_ids == ("E01", "E02", "E03")
    assert case.maintenance.repair_minutes == 120
    assert case.maintenance.manual_inspection_required is False


def test_brake_failure_requires_manual_inspection_even_when_route_exists(sqlite_factory):
    _seed(sqlite_factory)
    service = RescueOrchestrationService(
        SqlAlchemyVehicleOperationsRepository(sqlite_factory), SqlAlchemyRoadNetworkRepository(sqlite_factory), DijkstraPathFinder(), FixedClock()
    )

    case = service.orchestrate(BreakdownOrchestrationInput("TASK-ORCH-001", "V-001", "V-005", "N04", "COLD_CHAIN", "CRITICAL", "BRAKE_FAILURE"))

    assert case.maintenance.manual_inspection_required is True
    assert case.mission.outbound_edge_ids
    assert Decimal("0") < Decimal(case.maintenance.repair_minutes)


def test_orchestration_backfills_a_legacy_replacement_route_from_the_vehicle_node(sqlite_factory):
    _seed(sqlite_factory)
    repository = SqlAlchemyVehicleOperationsRepository(sqlite_factory)
    repository.create_breakdown_case(
        BreakdownCaseRequest(
            "TASK-ORCH-001", "V-001", "V-005", "RU-001", "N04", "N15",
            ("E20",), ("E20",), "ENGINE_COOLING", "发动机冷却系统故障", 120, False, NOW,
        )
    )
    service = RescueOrchestrationService(
        repository,
        SqlAlchemyRoadNetworkRepository(sqlite_factory),
        DijkstraPathFinder(),
        FixedClock(),
    )

    case = service.orchestrate(
        BreakdownOrchestrationInput(
            "TASK-ORCH-001", "V-001", "V-005", "N04", "COLD_CHAIN", "HIGH", "ENGINE_COOLING",
        )
    )

    assert case.replacement_edge_ids == ("E20",)
