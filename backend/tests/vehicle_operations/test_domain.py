from datetime import UTC, datetime, timedelta

import pytest

from app.vehicle_operations.models import (
    InvalidStateTransition,
    MaintenanceOrderSnapshot,
    MaintenanceStatus,
    RescueMissionSnapshot,
    RescueStatus,
    VehicleOperationalStatus,
    require_maintenance_transition,
    require_rescue_transition,
    require_vehicle_transition,
)

NOW = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (VehicleOperationalStatus.IN_TRANSIT, VehicleOperationalStatus.BROKEN),
        (VehicleOperationalStatus.BROKEN, VehicleOperationalStatus.WAITING_RESCUE),
        (VehicleOperationalStatus.WAITING_RESCUE, VehicleOperationalStatus.IN_RESCUE),
        (VehicleOperationalStatus.IN_RESCUE, VehicleOperationalStatus.MAINTENANCE),
        (VehicleOperationalStatus.MAINTENANCE, VehicleOperationalStatus.QA_PENDING),
        (VehicleOperationalStatus.QA_PENDING, VehicleOperationalStatus.AVAILABLE),
        (VehicleOperationalStatus.QA_PENDING, VehicleOperationalStatus.OUT_OF_SERVICE),
    ],
)
def test_vehicle_state_machine_accepts_only_realistic_forward_transitions(current, target):
    require_vehicle_transition(current, target)


def test_vehicle_state_machine_rejects_skipping_repair():
    with pytest.raises(InvalidStateTransition, match="BROKEN.*AVAILABLE"):
        require_vehicle_transition(VehicleOperationalStatus.BROKEN, VehicleOperationalStatus.AVAILABLE)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RescueStatus.CREATED, RescueStatus.DISPATCHED),
        (RescueStatus.DISPATCHED, RescueStatus.ARRIVED),
        (RescueStatus.ARRIVED, RescueStatus.LOADED),
        (RescueStatus.LOADED, RescueStatus.DELIVERED),
    ],
)
def test_rescue_state_machine_advances_one_stage_at_a_time(current, target):
    require_rescue_transition(current, target)


def test_rescue_state_machine_rejects_direct_delivery():
    with pytest.raises(InvalidStateTransition):
        require_rescue_transition(RescueStatus.DISPATCHED, RescueStatus.DELIVERED)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (MaintenanceStatus.SCHEDULED, MaintenanceStatus.WAITING_BAY),
        (MaintenanceStatus.WAITING_BAY, MaintenanceStatus.DIAGNOSING),
        (MaintenanceStatus.DIAGNOSING, MaintenanceStatus.REPAIRING),
        (MaintenanceStatus.REPAIRING, MaintenanceStatus.QA_PENDING),
        (MaintenanceStatus.QA_PENDING, MaintenanceStatus.COMPLETED),
        (MaintenanceStatus.QA_PENDING, MaintenanceStatus.FAILED),
    ],
)
def test_maintenance_state_machine_requires_diagnosis_repair_and_qa(current, target):
    require_maintenance_transition(current, target)


def test_snapshots_report_progress_and_countdown_without_mutating_state():
    rescue = RescueMissionSnapshot(
        mission_no="JY-20260910-001",
        task_id="TASK-1",
        vehicle_id="V-001",
        rescue_unit_id="RU-001",
        status=RescueStatus.ARRIVED,
        incident_node_id="N04",
        station_node_id="N15",
        outbound_edge_ids=("E20",),
        tow_edge_ids=("E20",),
        next_transition_at=NOW + timedelta(seconds=15),
        version=2,
    )
    maintenance = MaintenanceOrderSnapshot(
        order_no="WX-20260910-018",
        task_id="TASK-1",
        vehicle_id="V-001",
        bay_code="A-02",
        status=MaintenanceStatus.REPAIRING,
        fault_code="ENGINE_COOLING",
        diagnosis="发动机冷却系统故障",
        repair_minutes=120,
        manual_inspection_required=False,
        next_transition_at=NOW + timedelta(seconds=25),
        available_after=NOW + timedelta(seconds=40),
        version=4,
    )

    assert rescue.progress_percent == 50
    assert maintenance.progress_percent == 68
    assert maintenance.seconds_remaining(NOW) == 40
