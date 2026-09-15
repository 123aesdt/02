from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.fleet_vehicle import FleetVehicle
from app.models.order import Order
from app.models.task import DispatchTask
from app.models.vehicle_operation import DomainOutbox, MaintenanceBay, RescueUnit, VehicleStatusHistory
from app.sandtable.sqlalchemy_repository import seed_new_county_sandtable
from app.vehicle_operations.models import BreakdownCaseRequest
from app.vehicle_operations.sqlalchemy_repository import SqlAlchemyVehicleOperationsRepository

NOW = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)


def _seed(factory) -> None:
    with factory() as session:
        seed_new_county_sandtable(session)
        order = session.scalar(select(Order).where(Order.order_no == "DEMO-ORDER-001"))
        assert order is not None
        session.add(
            DispatchTask(
                task_id="TASK-RESCUE-001",
                order_id=order.id,
                status="APPROVED",
                idempotency_key="rescue-case-001",
            )
        )
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


def _request(*, manual: bool = False) -> BreakdownCaseRequest:
    return BreakdownCaseRequest(
        task_id="TASK-RESCUE-001",
        vehicle_id="V-001",
        replacement_vehicle_id="V-005",
        rescue_unit_id="RU-001",
        incident_node_id="N04",
        station_node_id="N15",
        outbound_edge_ids=("E20",),
        tow_edge_ids=("E20",),
        fault_code="ENGINE_COOLING",
        diagnosis="发动机冷却系统故障",
        repair_minutes=120,
        manual_inspection_required=manual,
        occurred_at=NOW,
    )


def test_breakdown_case_is_atomic_idempotent_and_records_outbox(sqlite_factory):
    _seed(sqlite_factory)
    repository = SqlAlchemyVehicleOperationsRepository(sqlite_factory)

    first = repository.create_breakdown_case(_request())
    repeated = repository.create_breakdown_case(_request())

    assert repeated.mission.mission_no == first.mission.mission_no
    assert repeated.maintenance.order_no == first.maintenance.order_no
    assert first.vehicle_status == "WAITING_RESCUE"
    assert first.replacement_vehicle_status == "IN_TRANSIT"
    with sqlite_factory() as session:
        assert session.scalar(select(FleetVehicle.status).where(FleetVehicle.vehicle_id == "V-001")) == "WAITING_RESCUE"
        assert session.scalar(select(FleetVehicle.status).where(FleetVehicle.vehicle_id == "V-005")) == "IN_TRANSIT"
        assert len(list(session.scalars(select(VehicleStatusHistory)))) == 4
        event_types = set(session.scalars(select(DomainOutbox.event_type)))
        assert {"VEHICLE_STOPPED", "REPLACEMENT_DISPATCHED", "RESCUE_DISPATCHED", "MAINTENANCE_SCHEDULED"} <= event_types


def test_repair_eta_starts_when_repairing_begins_and_uses_estimated_minutes(sqlite_factory):
    _seed(sqlite_factory)
    repository = SqlAlchemyVehicleOperationsRepository(sqlite_factory)

    created = repository.create_breakdown_case(_request())
    assert created.maintenance.available_after is None

    for elapsed in (8, 14, 18):
        repository.advance_one_due_rescue(NOW + timedelta(seconds=elapsed))
    repository.advance_one_due_maintenance(NOW + timedelta(seconds=19))
    repairing = repository.advance_one_due_maintenance(NOW + timedelta(seconds=24))

    assert repairing is not None
    assert repairing.maintenance.status == "REPAIRING"
    assert repairing.maintenance.available_after == NOW + timedelta(minutes=120, seconds=30)
    assert repository.advance_one_due_maintenance(NOW + timedelta(seconds=49)) is None


def test_due_progression_tows_repairs_inspects_and_returns_vehicle_to_available(sqlite_factory):
    _seed(sqlite_factory)
    repository = SqlAlchemyVehicleOperationsRepository(sqlite_factory)
    repository.create_breakdown_case(_request())

    for elapsed in (8, 14, 18):
        assert repository.advance_one_due_rescue(NOW + timedelta(seconds=elapsed)) is not None
    for elapsed in (
        timedelta(seconds=19),
        timedelta(seconds=24),
        timedelta(minutes=120, seconds=24),
        timedelta(minutes=120, seconds=30),
    ):
        assert repository.advance_one_due_maintenance(NOW + elapsed) is not None

    case = repository.get_case("TASK-RESCUE-001")
    assert case is not None
    assert case.mission.status == "DELIVERED"
    assert case.maintenance.status == "COMPLETED"
    assert case.maintenance.inspection_result == "PASSED"
    assert case.vehicle_status == "AVAILABLE"


def test_manual_inspection_holds_vehicle_until_an_authorized_decision(sqlite_factory):
    _seed(sqlite_factory)
    repository = SqlAlchemyVehicleOperationsRepository(sqlite_factory)
    repository.create_breakdown_case(_request(manual=True))
    for elapsed in (8, 14, 18):
        repository.advance_one_due_rescue(NOW + timedelta(seconds=elapsed))
    for elapsed in (
        timedelta(seconds=19),
        timedelta(seconds=24),
        timedelta(minutes=120, seconds=24),
    ):
        repository.advance_one_due_maintenance(NOW + elapsed)

    waiting = repository.get_case("TASK-RESCUE-001")
    assert waiting is not None
    assert waiting.maintenance.status == "QA_PENDING"
    assert waiting.vehicle_status == "QA_PENDING"

    repository.record_inspection(
        "WX-20260910-001",
        passed=False,
        decided_at=NOW + timedelta(minutes=120, seconds=30),
        decided_by="CF-DEMO-003",
    )
    failed = repository.get_case("TASK-RESCUE-001")
    assert failed is not None
    assert failed.maintenance.status == "FAILED"
    assert failed.vehicle_status == "OUT_OF_SERVICE"
