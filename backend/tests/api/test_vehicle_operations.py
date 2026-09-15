
from fastapi import FastAPI
from fastapi.testclient import TestClient
from security_support import authorize_app

from app.security.permissions import Role


class FakeVehicleOperationsService:
    def __init__(self):
        self.decisions = []

    def map_snapshot(self, task_id):
        return {
            "task_id": task_id,
            "incident": {"status": "AUTO_PROCESSING"},
            "nodes": [],
            "edges": [],
            "vehicles": [],
            "routes": [],
            "timeline": [],
        }

    def driver_map_snapshot(self, task_id, principal):
        return {
            "task_id": task_id,
            "viewer": principal.subject_id,
            "incident": {"status": "AUTO_PROCESSING"},
            "nodes": [],
            "edges": [],
            "vehicles": [],
            "routes": [],
            "timeline": [],
        }

    def list_vehicles(self):
        return []

    def get_rescue_mission(self, mission_no):
        return {"mission_no": mission_no, "status": "DISPATCHED"}

    def retry_rescue_mission(self, mission_no):
        return {"mission_no": mission_no, "status": "DISPATCHED"}

    def list_maintenance_orders(self):
        return []

    def get_maintenance_order(self, order_no):
        return {"order_no": order_no, "status": "QA_PENDING"}

    def record_inspection(self, order_no, passed, principal):
        self.decisions.append((order_no, passed, principal.subject_id))
        return {"order_no": order_no, "status": "COMPLETED" if passed else "FAILED"}


def application(service, role=Role.ADMIN):
    from app.api.v1.vehicle_operations import router

    app = authorize_app(FastAPI(), role)
    app.state.vehicle_operations_api_service = service
    app.include_router(router)
    return app


def test_map_snapshot_is_available_to_dispatch_supervisors():
    response = TestClient(application(FakeVehicleOperationsService(), Role.SUPERVISOR)).get("/api/v1/map/snapshot?task_id=TASK-1")

    assert response.status_code == 200
    assert response.json()["task_id"] == "TASK-1"


def test_employee_cannot_read_the_command_center_snapshot():
    response = TestClient(application(FakeVehicleOperationsService(), Role.EMPLOYEE)).get("/api/v1/map/snapshot?task_id=TASK-1")

    assert response.status_code == 403


def test_employee_can_read_own_vehicle_operation_snapshot_only():
    response = TestClient(application(FakeVehicleOperationsService(), Role.EMPLOYEE)).get(
        "/api/v1/driver/operation-snapshot?task_id=TASK-1"
    )

    assert response.status_code == 200
    assert response.json()["viewer"] == "test-employee"


def test_inspection_decision_uses_authenticated_identity():
    service = FakeVehicleOperationsService()
    response = TestClient(application(service, Role.SUPERVISOR)).post(
        "/api/v1/maintenance-orders/WX-20260910-001/inspection-decisions",
        json={"passed": True},
    )

    assert response.status_code == 200
    assert service.decisions == [("WX-20260910-001", True, "test-supervisor")]
    assert response.json()["status"] == "COMPLETED"
