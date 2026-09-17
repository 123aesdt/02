from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm.exc import StaleDataError

from app.core.config import get_settings
from app.demo_reset import DemoScenarioResetService
from app.main import create_app
from app.models.fleet_driver import FleetDriver
from app.models.fleet_vehicle import FleetVehicle
from app.models.road import RoadEdge
from app.models.vehicle_operation import MaintenanceBay, MaintenanceOrder, RescueMission, RescueUnit
from app.security.permissions import Role
from app.seed import seed_database
from tests.api.test_endpoint_permissions import auth, headers


@pytest.fixture(autouse=True)
def clear_settings_cache():
    yield
    get_settings.cache_clear()


def _client(monkeypatch, sqlite_factory, *, profile: str = "docker-dev", subject_id: str = "CF-DEMO-001") -> TestClient:
    monkeypatch.setenv("RUNTIME_PROFILE", "test")
    monkeypatch.setenv("AUTHENTICATION_PROVIDER", "disabled")
    monkeypatch.setenv("DATABASE_URL", str(sqlite_factory.kw["bind"].url))
    get_settings.cache_clear()
    dependencies = auth(Role.EMPLOYEE)
    provider = dependencies["authentication_provider"]
    provider.principal = replace(provider.principal, subject_id=subject_id)
    app = create_app(
        workspace_read_service=object(),
        shared_memory_service=object(),
        demo_scenario_reset_service=DemoScenarioResetService(sqlite_factory),
        **dependencies,
    )
    app.state.runtime_profile = profile
    return TestClient(app)


def _dirty_vehicle_demo(sqlite_factory) -> None:
    seed_database(session_factory=sqlite_factory, runtime_profile="docker-dev")
    with sqlite_factory() as session, session.begin():
        vehicles = {
            row.vehicle_id: row
            for row in session.scalars(
                select(FleetVehicle).where(FleetVehicle.vehicle_id.in_(("V-002", "V-003", "V-011")))
            )
        }
        vehicles["V-002"].status = "MAINTENANCE"
        vehicles["V-002"].current_node_id = "N15"
        vehicles["V-002"].fault_code = "ENGINE_COOLING"
        vehicles["V-002"].maintenance_order_no = "WX-DEMO"
        vehicles["V-003"].status = "IN_TRANSIT"
        vehicles["V-011"].status = "RESERVED"
        for edge in session.scalars(select(RoadEdge).where(RoadEdge.edge_id.in_(("E04", "E10")))):
            edge.status = "BLOCKED"
        mission = session.scalar(select(RescueMission).order_by(RescueMission.id))
        order = session.scalar(select(MaintenanceOrder).order_by(MaintenanceOrder.id))
        unit = session.scalar(select(RescueUnit).where(RescueUnit.unit_id == "RU-001"))
        bay = session.scalar(select(MaintenanceBay).where(MaintenanceBay.bay_code == "A-02"))
        assert mission is not None and order is not None and unit is not None and bay is not None
        mission.vehicle_id = "V-002"
        mission.status = "DISPATCHED"
        order.vehicle_id = "V-002"
        order.status = "REPAIRING"
        unit.status = "DISPATCHED"
        bay.status = "OCCUPIED"
        bay.current_order_no = order.order_no


def test_demo_employee_resets_vehicle_scenario_for_another_full_run(monkeypatch, sqlite_factory) -> None:
    _dirty_vehicle_demo(sqlite_factory)

    response = _client(monkeypatch, sqlite_factory).post(
        "/api/v1/demo-scenarios/VEHICLE_BREAKDOWN_N04/reset",
        headers=headers(),
    )

    assert response.status_code == 200
    assert response.json() == {
        "scenario_id": "VEHICLE_BREAKDOWN_N04",
        "status": "READY",
        "message": "演示场景已恢复，可以再次提交。",
    }
    with sqlite_factory() as session:
        vehicles = {
            row.vehicle_id: (row.status, row.current_node_id, row.assigned_driver_id, row.fault_code, row.maintenance_order_no)
            for row in session.scalars(
                select(FleetVehicle).where(FleetVehicle.vehicle_id.in_(("V-002", "V-003", "V-011")))
            )
        }
        drivers = {
            row.driver_id: (row.status, row.current_vehicle_id)
            for row in session.scalars(
                select(FleetDriver).where(FleetDriver.driver_id.in_(("D-002", "D-011", "D-012")))
            )
        }
        assert vehicles == {
            "V-002": ("IN_TRANSIT", "N01", "D-002", None, None),
            "V-003": ("AVAILABLE", "N15", "D-011", None, None),
            "V-011": ("AVAILABLE", "N14", "D-012", None, None),
        }
        assert drivers == {
            "D-002": ("ON_DUTY", "V-002"),
            "D-011": ("ON_DUTY", "V-003"),
            "D-012": ("ON_DUTY", "V-011"),
        }
        assert set(session.scalars(select(RoadEdge.status).where(RoadEdge.edge_id.in_(("E04", "E10"))))) == {"OPEN"}
        assert set(session.scalars(select(RescueMission.status))) == {"CANCELLED"}
        assert set(session.scalars(select(MaintenanceOrder.status))) == {"CANCELLED"}
        assert set(session.scalars(select(RescueUnit.status))) == {"AVAILABLE"}
        assert set(session.scalars(select(MaintenanceBay.status))) == {"AVAILABLE"}


def test_demo_reset_is_hidden_outside_docker_demo(monkeypatch, sqlite_factory) -> None:
    _dirty_vehicle_demo(sqlite_factory)

    response = _client(monkeypatch, sqlite_factory, profile="local").post(
        "/api/v1/demo-scenarios/VEHICLE_BREAKDOWN_N04/reset",
        headers=headers(),
    )

    assert response.status_code == 404


def test_demo_reset_rejects_non_whitelisted_employee(monkeypatch, sqlite_factory) -> None:
    _dirty_vehicle_demo(sqlite_factory)

    response = _client(monkeypatch, sqlite_factory, subject_id="employee-1").post(
        "/api/v1/demo-scenarios/VEHICLE_BREAKDOWN_N04/reset",
        headers=headers(),
    )

    assert response.status_code == 403


def test_second_demo_employee_can_reset_the_road_scenario(monkeypatch, sqlite_factory) -> None:
    _dirty_vehicle_demo(sqlite_factory)

    response = _client(monkeypatch, sqlite_factory, subject_id="CF-DEMO-006").post(
        "/api/v1/demo-scenarios/ROAD_BLOCKED_E04/reset",
        headers=headers(),
    )

    assert response.status_code == 200
    assert response.json()["scenario_id"] == "ROAD_BLOCKED_E04"
    with sqlite_factory() as session:
        assert set(
            session.scalars(select(RoadEdge.status).where(RoadEdge.edge_id.in_(("E04", "E10"))))
        ) == {"OPEN"}
        vehicle = session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == "V-002"))
        assert vehicle is not None
        assert vehicle.status == "MAINTENANCE"


def test_incomplete_demo_state_rolls_back_without_partial_reset(monkeypatch, sqlite_factory) -> None:
    _dirty_vehicle_demo(sqlite_factory)
    with sqlite_factory() as session, session.begin():
        session.execute(delete(RoadEdge).where(RoadEdge.edge_id == "E10"))

    response = _client(monkeypatch, sqlite_factory).post(
        "/api/v1/demo-scenarios/VEHICLE_BREAKDOWN_N04/reset",
        headers=headers(),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "DEMO_SCENARIO_STATE_INCOMPLETE"
    with sqlite_factory() as session:
        road = session.scalar(select(RoadEdge).where(RoadEdge.edge_id == "E04"))
        vehicle = session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == "V-002"))
        assert road is not None and road.status == "BLOCKED"
        assert vehicle is not None and vehicle.status == "MAINTENANCE"


class ConflictingResetService:
    def reset(self, scenario_id: str, *, principal_subject_id: str):
        raise StaleDataError("concurrent demo progress update")


def test_concurrent_demo_progress_returns_retryable_conflict(monkeypatch, sqlite_factory) -> None:
    _dirty_vehicle_demo(sqlite_factory)
    client = _client(monkeypatch, sqlite_factory)
    client.app.state.demo_scenario_reset_service = ConflictingResetService()

    response = client.post(
        "/api/v1/demo-scenarios/VEHICLE_BREAKDOWN_N04/reset",
        headers=headers(),
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "DEMO_SCENARIO_RESET_CONFLICT",
        "message": "演示状态正在更新，请重试复位。",
    }
