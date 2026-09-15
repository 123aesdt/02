from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.models.anomaly import Anomaly
from app.models.fleet_vehicle import FleetVehicle
from app.models.task import DispatchTask
from app.models.vehicle_operation import MaintenanceBay, MaintenanceOrder, RescueMission, RescueUnit
from app.seed import migrate_legacy_employee_operation_case, seed_database


def test_development_seed_creates_idempotent_vehicle_rescue_demo_case(sqlite_factory):
    seed_database(session_factory=sqlite_factory, runtime_profile="test")
    seed_database(session_factory=sqlite_factory, runtime_profile="test")

    with sqlite_factory() as session:
        missions = list(
            session.scalars(
                select(RescueMission).where(
                    RescueMission.task_id == "DEMO-TASK-REPORT-VEHICLE"
                )
            )
        )
        orders = list(
            session.scalars(
                select(MaintenanceOrder).where(
                    MaintenanceOrder.task_id == "DEMO-TASK-REPORT-VEHICLE"
                )
            )
        )
        demo_breakdown = session.scalar(select(Anomaly).where(Anomaly.anomaly_no == "DEMO-ANOM-004"))
        map_task = session.scalar(
            select(DispatchTask).where(
                DispatchTask.task_id == "DEMO-TASK-REPORT-VEHICLE"
            )
        )

    assert len(missions) == 1
    assert missions[0].vehicle_id == "V-001"
    assert missions[0].rescue_unit_id == "RU-001"
    assert len(orders) == 1
    assert orders[0].bay_code == "A-02"
    assert demo_breakdown is not None
    assert map_task is not None
    assert map_task.anomaly_id == demo_breakdown.id


def test_docker_development_seed_keeps_report_source_task_free_of_fake_breakdown(sqlite_factory):
    seed_database(session_factory=sqlite_factory, runtime_profile="docker-dev")

    with sqlite_factory() as session:
        mission = session.scalar(select(RescueMission).where(RescueMission.task_id == "DEMO-TASK-REPORT-002"))
        task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == "DEMO-TASK-REPORT-002"))

    assert mission is None
    assert task is not None
    assert task.assignee_subject_id == "CF-DEMO-001"


def test_seed_migration_removes_legacy_employee_operation_and_releases_resources(sqlite_factory):
    seed_database(session_factory=sqlite_factory, runtime_profile="test")
    occurred_at = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)

    with sqlite_factory() as session, session.begin():
        vehicle = session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == "V-002"))
        assert vehicle is not None
        unit = RescueUnit(
            unit_id="RU-LEGACY",
            name="遗留救援车",
            plate_no="新救援-LEGACY",
            unit_type="TOW_TRUCK",
            status="DISPATCHED",
            current_node_id="N15",
            capacity_tons=Decimal("5.00"),
        )
        bay = MaintenanceBay(
            bay_code="LEGACY-01",
            station_id="ST-007",
            status="RESERVED",
            current_order_no="WX-LEGACY-002",
        )
        mission = RescueMission(
            mission_no="JY-LEGACY-002",
            task_id="DEMO-TASK-REPORT-002",
            vehicle_id="V-002",
            rescue_unit_id="RU-LEGACY",
            status="DELIVERED",
            incident_node_id="N04",
            station_node_id="N15",
            outbound_edge_ids=["E20"],
            tow_edge_ids=["E20"],
            next_transition_at=None,
            attempt_count=1,
        )
        order = MaintenanceOrder(
            order_no="WX-LEGACY-002",
            task_id="DEMO-TASK-REPORT-002",
            vehicle_id="V-002",
            bay_code="LEGACY-01",
            status="REPAIRING",
            fault_code="ENGINE_COOLING",
            diagnosis="旧版本自动创建的维修",
            repair_minutes=120,
            manual_inspection_required=False,
            next_transition_at=None,
            available_after=occurred_at,
        )
        session.add_all((unit, bay, mission, order))
        vehicle.status = "MAINTENANCE"
        vehicle.status_reason = "旧版本错误处置"
        vehicle.fault_code = "ENGINE_COOLING"
        vehicle.maintenance_order_no = order.order_no
        vehicle.available_after = occurred_at

    with sqlite_factory() as session, session.begin():
        migrate_legacy_employee_operation_case(session)

    with sqlite_factory() as session:
        mission = session.scalar(select(RescueMission).where(RescueMission.task_id == "DEMO-TASK-REPORT-002"))
        order = session.scalar(select(MaintenanceOrder).where(MaintenanceOrder.task_id == "DEMO-TASK-REPORT-002"))
        vehicle = session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == "V-002"))
        unit = session.scalar(select(RescueUnit).where(RescueUnit.unit_id == "RU-LEGACY"))
        bay = session.scalar(select(MaintenanceBay).where(MaintenanceBay.bay_code == "LEGACY-01"))

    assert mission is None
    assert order is None
    assert vehicle is not None
    assert vehicle.status == "IN_TRANSIT"
    assert vehicle.maintenance_order_no is None
    assert unit is not None and unit.status == "AVAILABLE"
    assert bay is not None and bay.status == "AVAILABLE"
