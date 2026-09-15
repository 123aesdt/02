from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.anomaly_reports import (
    AnomalyReportResult,
    ReportIdempotencyConflict,
    ReportQueueUnavailable,
    ReportSourceForbidden,
    SourceContextIncomplete,
    SourceTaskEnded,
    SourceTaskNotFound,
    SourceTaskNotReportable,
)
from app.main import create_app
from app.security.permissions import Role
from tests.api.test_endpoint_permissions import auth, headers


def payload() -> dict[str, object]:
    return {
        "source_task_id": "TASK-OWNED",
        "anomaly_type": "VEHICLE_BREAKDOWN",
        "description": "车辆行驶时出现异响，无法继续安全行驶。",
        "location_text": "新平路南段物流站入口",
        "reported_vehicle_status": "BROKEN",
        "severity": "HIGH",
        "incident_node_id": "N04",
        "affected_edge_id": None,
        "idempotency_key": "driver-report-uuid",
    }


@dataclass
class ReportService:
    error: Exception | None = None

    def __post_init__(self) -> None:
        self.commands = []
        self.subject_id = None

    async def submit(self, command, *, principal_subject_id: str):
        self.commands.append(command)
        self.subject_id = principal_subject_id
        if self.error is not None:
            raise self.error
        return AnomalyReportResult(
            anomaly_id=42,
            anomaly_no="ANOM-example",
            task_id="TASK-NEW",
            status="PENDING",
            duplicate=False,
        )


def test_employee_report_returns_202_and_uses_authenticated_subject() -> None:
    service = ReportService()
    dependencies = auth(Role.EMPLOYEE)
    audit_repository = dependencies["security_audit_repository"]
    app = create_app(anomaly_report_service=service, **dependencies)

    response = TestClient(app).post("/api/v1/anomaly-reports", headers=headers(), json=payload())

    assert response.status_code == 202
    assert response.json() == {
        "anomaly_id": 42,
        "anomaly_no": "ANOM-example",
        "task_id": "TASK-NEW",
        "status": "PENDING",
        "accepted": True,
        "duplicate": False,
        "message": "问题已上报，AI 调度已启动。",
    }
    assert service.subject_id == "employee-1"
    assert service.commands[0].incident_node_id == "N04"
    assert service.commands[0].affected_edge_id is None
    assert any(
        event.event_type.value == "ANOMALY_REPORT"
        and event.reason_code == "ANOMALY_REPORT_ACCEPTED"
        for event in audit_repository.events
    )


def test_dispatcher_cannot_report_or_reach_service() -> None:
    service = ReportService()
    app = create_app(anomaly_report_service=service, **auth(Role.DISPATCHER))

    response = TestClient(app).post("/api/v1/anomaly-reports", headers=headers(), json=payload())

    assert response.status_code == 403
    assert response.json()["code"] == "AUTHORIZATION_DENIED"
    assert service.commands == []


def test_report_request_rejects_client_supplied_dispatch_context() -> None:
    service = ReportService()
    app = create_app(anomaly_report_service=service, **auth(Role.EMPLOYEE))
    spoofed = {
        **payload(),
        "order_id": 999,
        "driver_id": "another-driver",
        "vehicle_id": "another-vehicle",
        "route_id": "another-route",
        "assignee_employee_id": "another-employee",
    }

    response = TestClient(app).post(
        "/api/v1/anomaly-reports",
        headers=headers(),
        json=spoofed,
    )

    assert response.status_code == 422
    assert service.commands == []


@pytest.mark.parametrize(
    ("anomaly_type", "vehicle_status"),
    [
        ("VEHICLE_BREAKDOWN", "NORMAL"),
        ("ROAD_BLOCKED", "BROKEN"),
        ("WEATHER", "MAINTENANCE"),
    ],
)
def test_report_request_rejects_inconsistent_problem_and_vehicle_status(
    anomaly_type: str,
    vehicle_status: str,
) -> None:
    service = ReportService()
    app = create_app(anomaly_report_service=service, **auth(Role.EMPLOYEE))
    invalid = {
        **payload(),
        "anomaly_type": anomaly_type,
        "reported_vehicle_status": vehicle_status,
    }

    response = TestClient(app).post("/api/v1/anomaly-reports", headers=headers(), json=invalid)

    assert response.status_code == 422
    assert service.commands == []


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (ReportSourceForbidden(), 403, "REPORT_SOURCE_FORBIDDEN"),
        (SourceTaskNotFound(), 404, "SOURCE_TASK_NOT_FOUND"),
        (SourceTaskNotReportable(), 409, "SOURCE_TASK_NOT_REPORTABLE"),
        (SourceTaskEnded(), 409, "SOURCE_TASK_ENDED"),
        (ReportIdempotencyConflict(), 409, "IDEMPOTENCY_CONFLICT"),
        (SourceContextIncomplete(), 422, "SOURCE_CONTEXT_INCOMPLETE"),
    ],
)
def test_report_errors_have_stable_http_contract(error, expected_status, expected_code) -> None:
    app = create_app(anomaly_report_service=ReportService(error), **auth(Role.EMPLOYEE))

    response = TestClient(app).post("/api/v1/anomaly-reports", headers=headers(), json=payload())

    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code


def test_queue_unavailable_returns_saved_identities_without_internal_details() -> None:
    app = create_app(
        anomaly_report_service=ReportService(
            ReportQueueUnavailable(
                anomaly_id=42,
                anomaly_no="ANOM-example",
                task_id="TASK-SAVED",
            )
        ),
        **auth(Role.EMPLOYEE),
    )

    response = TestClient(app).post("/api/v1/anomaly-reports", headers=headers(), json=payload())

    assert response.status_code == 503
    assert response.json() == {
        "code": "REPORT_QUEUE_UNAVAILABLE",
        "message": "问题已保存，但 AI 调度暂未启动。请使用相同内容重试。",
        "anomaly_id": 42,
        "anomaly_no": "ANOM-example",
        "task_id": "TASK-SAVED",
        "retryable": True,
    }
    assert "redis" not in response.text.lower()
    assert "temporary" not in response.text.lower()
    assert "internal" not in response.text.lower()
