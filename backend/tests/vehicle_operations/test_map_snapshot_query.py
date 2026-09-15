from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.order import Order
from app.models.task import DispatchTask
from app.models.vehicle_operation import MaintenanceBay, RescueUnit
from app.sandtable.sqlalchemy_repository import seed_new_county_sandtable
from app.vehicle_operations.models import (
    BreakdownCaseRequest,
    MaintenanceStatus,
    RescueStatus,
)
from app.vehicle_operations.query_service import VehicleOperationsQueryService
from app.vehicle_operations.sqlalchemy_repository import SqlAlchemyVehicleOperationsRepository, VehicleOperationNotFound

NOW = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)


def test_map_snapshot_combines_topology_physical_routes_and_maintenance_state(sqlite_factory):
    with sqlite_factory() as session:
        seed_new_county_sandtable(session)
        order = session.scalar(select(Order).where(Order.order_no == "DEMO-ORDER-001"))
        assert order is not None
        session.add(DispatchTask(task_id="TASK-MAP-001", order_id=order.id, status="APPROVED", idempotency_key="map-1", assignee_subject_id="employee-1"))
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
    repository = SqlAlchemyVehicleOperationsRepository(sqlite_factory)
    repository.create_breakdown_case(
        BreakdownCaseRequest(
            "TASK-MAP-001", "V-001", "V-005", "RU-001", "N04", "N15", ("E20",), ("E20",), "ENGINE_COOLING", "发动机冷却系统故障", 120, False, NOW,
            replacement_edge_ids=("E01", "E02", "E03"),
        )
    )

    snapshot = VehicleOperationsQueryService(sqlite_factory, repository, clock=lambda: NOW).map_snapshot("TASK-MAP-001")

    assert len(snapshot["nodes"]) == 22
    assert len(snapshot["edges"]) == 36
    assert {route["kind"]: route["edge_ids"] for route in snapshot["routes"]} == {
        "REPLACEMENT": ["E01", "E02", "E03"],
        "RESCUE": ["E20"],
        "TOW": ["E20"],
        "INTERRUPTED": ["E03"],
    }
    assert snapshot["incident"]["vehicle_id"] == "V-001"
    replacement_route = next(route for route in snapshot["routes"] if route["kind"] == "REPLACEMENT")
    assert replacement_route["node_ids"] == ["N01", "N02", "N03", "N04"]
    incident_vehicle = next(vehicle for vehicle in snapshot["vehicles"] if vehicle["vehicle_id"] == "V-001")
    assert incident_vehicle["max_load_kg"] == "1500.00"
    assert incident_vehicle["current_load_kg"] == "700.00"
    assert incident_vehicle["assigned_driver_id"] == "D-001"
    assert incident_vehicle["status_reason"]
    assert incident_vehicle["available_after"] is None
    assert snapshot["maintenance"]["available_after"] is None
    assert snapshot["maintenance"]["countdown_seconds"] is None
    assert snapshot["maintenance"]["order_no"] == "WX-20260910-001"
    assert snapshot["timeline"][0]["event_type"] == "VEHICLE_STOPPED"

    service = VehicleOperationsQueryService(sqlite_factory, repository, clock=lambda: NOW)
    own_snapshot = service.driver_map_snapshot("TASK-MAP-001", SimpleNamespace(subject_id="employee-1"))
    assert own_snapshot["task_id"] == "TASK-MAP-001"
    with pytest.raises(VehicleOperationNotFound):
        service.driver_map_snapshot("TASK-MAP-001", SimpleNamespace(subject_id="employee-2"))


def test_stage_projection_does_not_present_failed_or_cancelled_work_as_completed():
    case = SimpleNamespace(
        replacement_vehicle_id=None,
        mission=SimpleNamespace(status=RescueStatus.FAILED, progress_percent=100),
        maintenance=SimpleNamespace(status=MaintenanceStatus.CANCELLED, progress_percent=100),
    )

    stages = VehicleOperationsQueryService._stages(case)

    assert [stage["status"] for stage in stages] == [
        "COMPLETED",
        "SKIPPED",
        "FAILED",
        "CANCELLED",
    ]
    assert stages[1]["detail"] == "当前任务未启用替代车辆"


def test_maintenance_events_are_localized_for_the_employee_timeline():
    assert VehicleOperationsQueryService._event_label("MAINTENANCE_DIAGNOSING") == "维修人员开始故障诊断"
    assert VehicleOperationsQueryService._event_label("MAINTENANCE_REPAIRING") == "车辆开始维修"
    assert VehicleOperationsQueryService._event_label("MAINTENANCE_QA_PENDING") == "维修完成，等待安全质检"
    assert VehicleOperationsQueryService._event_label("MAINTENANCE_COMPLETED") == "安全质检通过，维修工单完成"
