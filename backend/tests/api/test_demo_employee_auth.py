from datetime import datetime

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.security.demo_employee_accounts import DemoEmployee, DemoEmployeeSessionService
from app.security.development_session import DevelopmentSessionIssuer
from app.security.permissions import Role


class Revocations:
    async def is_revoked(self, jti: str) -> bool:
        return False

    async def revoke(self, jti: str, expires_at: datetime) -> None:
        return None


class EmployeeRepository:
    def __init__(self) -> None:
        self.accounts = (
            DemoEmployee("CF-DEMO-001", "张师傅", Role.EMPLOYEE),
            DemoEmployee("CF-DEMO-005", "系统管理员", Role.ADMIN),
            DemoEmployee("CF-DEMO-006", "陈师傅", Role.EMPLOYEE),
            DemoEmployee("CF-DEMO-007", "孙调度", Role.DISPATCHER),
        )

    def list_active(self) -> tuple[DemoEmployee, ...]:
        return self.accounts

    def get_active(self, employee_id: str) -> DemoEmployee | None:
        return next((item for item in self.accounts if item.employee_id == employee_id), None)


def build_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("RUNTIME_PROFILE", "local")
    monkeypatch.setenv("AUTHENTICATION_PROVIDER", "development_jwt")
    monkeypatch.setenv("DEVELOPMENT_JWT_SECRET", "demo-employee-api-secret-value-32-chars")
    monkeypatch.setenv("AUTH_ISSUER", "countyflow-dev")
    monkeypatch.setenv("AUTH_AUDIENCE", "countyflow-api")
    get_settings.cache_clear()
    issuer = DevelopmentSessionIssuer(
        "demo-employee-api-secret-value-32-chars",
        issuer="countyflow-dev",
        audience="countyflow-api",
        ttl_seconds=600,
    )
    service = DemoEmployeeSessionService(EmployeeRepository(), issuer)
    return TestClient(
        create_app(
            revocation_store=Revocations(),
            demo_employee_service=service,
        )
    )


def test_lists_active_demo_employees_without_internal_fields(monkeypatch) -> None:
    client = build_client(monkeypatch)

    response = client.get("/api/v1/auth/demo-employees")

    assert response.status_code == 200
    assert response.json() == [
        {"employee_id": "CF-DEMO-001", "display_name": "张师傅", "role": "EMPLOYEE"},
        {"employee_id": "CF-DEMO-005", "display_name": "系统管理员", "role": "ADMIN"},
        {"employee_id": "CF-DEMO-006", "display_name": "陈师傅", "role": "EMPLOYEE"},
        {"employee_id": "CF-DEMO-007", "display_name": "孙调度", "role": "DISPATCHER"},
    ]


def test_demo_session_derives_role_from_employee_record(monkeypatch) -> None:
    client = build_client(monkeypatch)

    response = client.post(
        "/api/v1/auth/demo-session",
        json={"employee_id": "cf-demo-001"},
    )

    assert response.status_code == 200
    assert response.json()["principal"]["subject_id"] == "CF-DEMO-001"
    assert response.json()["principal"]["roles"] == ["EMPLOYEE"]
    assert response.json()["principal"]["permissions"] == ["anomalies:report", "dispatch:read"]


def test_demo_session_rejects_unknown_employee_and_client_role(monkeypatch) -> None:
    client = build_client(monkeypatch)

    unknown = client.post("/api/v1/auth/demo-session", json={"employee_id": "CF-DEMO-999"})
    elevated = client.post(
        "/api/v1/auth/demo-session",
        json={"employee_id": "CF-DEMO-001", "role": "ADMIN"},
    )

    assert unknown.status_code == 404
    assert unknown.json()["code"] == "NOT_FOUND"
    assert elevated.status_code == 422


def test_demo_employee_endpoints_are_hidden_in_production(monkeypatch) -> None:
    client = build_client(monkeypatch)
    client.app.state.runtime_profile = "production"

    listed = client.get("/api/v1/auth/demo-employees")
    issued = client.post("/api/v1/auth/demo-session", json={"employee_id": "CF-DEMO-001"})

    assert listed.status_code == 404
    assert issued.status_code == 404
    assert "access_token" not in issued.text
