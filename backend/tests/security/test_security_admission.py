from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from security_support import authorize_app

from app.security.audit import SecurityAuditEventType, SecurityAuditStatus
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission, Role
from app.security.security_audit import SecurityAuditRecorder


class Repository:
    def __init__(self, *, fails: bool = False) -> None:
        self.events = []
        self.fails = fails

    def append(self, event) -> None:
        if self.fails:
            raise RuntimeError("database connection detail")
        self.events.append(event)


def protected_app(role: Role, repository: Repository) -> tuple[FastAPI, list[str]]:
    app = authorize_app(FastAPI(), role)
    app.state.security_audit_recorder = SecurityAuditRecorder(repository)
    calls = []
    principal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.MEMORY_MUTATE))]

    @app.post("/api/v1/memory/mutations")
    def mutate(_principal: principal):
        calls.append("mutated")
        return {"ok": True}

    return app, calls


def test_security_audit_denied() -> None:
    repository = Repository()
    app, calls = protected_app(Role.DISPATCHER, repository)

    response = TestClient(app).post("/api/v1/memory/mutations")

    assert response.status_code == 403
    assert calls == []
    assert len(repository.events) == 1
    event = repository.events[0]
    assert event.event_type is SecurityAuditEventType.MEMORY_MUTATION_DENIED
    assert event.status is SecurityAuditStatus.DENIED
    assert event.subject_id == "test-dispatcher"
    assert event.permission is Permission.MEMORY_MUTATE
    assert event.route_template == "/api/v1/memory/mutations"


def test_high_risk_security_audit_failure_fails_closed() -> None:
    app, calls = protected_app(Role.SUPERVISOR, Repository(fails=True))

    response = TestClient(app).post("/api/v1/memory/mutations")

    assert response.status_code == 503
    assert response.json()["code"] == "SECURITY_CONTROL_UNAVAILABLE"
    assert calls == []


def test_high_risk_allowed_admission_is_durable() -> None:
    repository = Repository()
    app, calls = protected_app(Role.SUPERVISOR, repository)

    response = TestClient(app).post("/api/v1/memory/mutations")

    assert response.status_code == 200
    assert calls == ["mutated"]
    assert repository.events[0].event_type is SecurityAuditEventType.SECURITY_ADMISSION
    assert repository.events[0].status is SecurityAuditStatus.ALLOWED
