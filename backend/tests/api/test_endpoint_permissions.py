from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import create_app
from app.security.models import AuthenticatedPrincipal, AuthMethod, Role
from app.security.permissions import ROLE_PERMISSION_MATRIX
from app.security.rate_limit import RateLimitDecision
from app.shared_memory.models import MemoryMutationResult, MutationDecision, MutationStatus, ProjectionStatus


class PrincipalProvider:
    def __init__(self, role: Role) -> None:
        now = datetime.now(UTC)
        self.principal = AuthenticatedPrincipal(
            subject_id=f"{role.value.lower()}-1",
            display_name=role.value.title(),
            roles=frozenset({role}),
            permissions=ROLE_PERMISSION_MATRIX[role],
            auth_method=AuthMethod.DEVELOPMENT_JWT,
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            jti=f"{role.value.lower()}-session",
        )

    async def authenticate(self, token: str) -> AuthenticatedPrincipal:
        return self.principal


class Revocations:
    async def is_revoked(self, jti: str) -> bool:
        return False

    async def revoke(self, jti: str, expires_at: datetime) -> None:
        return None


class AllowLimiter:
    async def admit(self, subject_id, operation):
        return RateLimitDecision(True, 100, 0, 1)


class SecurityRepository:
    def __init__(self) -> None:
        self.events = []

    def append(self, event) -> None:
        self.events.append(event)

    def list_recent(self, *, limit: int):
        return self.events[-limit:]


def auth(role: Role) -> dict[str, object]:
    return {
        "authentication_provider": PrincipalProvider(role),
        "revocation_store": Revocations(),
        "rate_limiter": AllowLimiter(),
        "security_audit_repository": SecurityRepository(),
    }


def headers() -> dict[str, str]:
    return {"Authorization": "Bearer signed-test-token"}


class OverrideService:
    def __init__(self) -> None:
        self.calls = 0

    async def apply(self, thread_id, request, principal=None):
        self.calls += 1
        raise AssertionError("unauthorized override reached the service")


class QueryService:
    pass


def override_payload() -> dict[str, object]:
    return {
        "idempotency_key": "override-security-1",
        "entity_type": "Vehicle",
        "entity_id": "vehicle-001",
        "field": "status",
        "old_value": "NORMAL",
        "new_value": "BROKEN",
        "reason": "inspection",
        "expected_version": 7,
        "expected_next_node": "capacity",
    }


def test_runtime_override_requires_permission() -> None:
    service = OverrideService()
    app = create_app(runtime_override_service=service, runtime_override_query_service=QueryService(), **auth(Role.DISPATCHER))

    response = TestClient(app).post("/api/v1/runtime/threads/thread-1/overrides", json=override_payload(), headers=headers())

    assert response.status_code == 403
    assert response.json()["code"] == "AUTHORIZATION_DENIED"
    assert service.calls == 0


class MemoryService:
    def __init__(self) -> None:
        self.commands = []

    async def mutate(self, command):
        self.commands.append(command)
        return MemoryMutationResult(
            mutation_id="mutation-1",
            fact_key="smf_" + "a" * 64,
            decision=MutationDecision.REPLACE,
            status=MutationStatus.APPLIED,
            before_version=1,
            after_version=2,
            vector_status=ProjectionStatus.NOT_REQUIRED,
            graph_status=ProjectionStatus.ACTIVE,
        )


def memory_payload() -> dict[str, object]:
    return {
        "idempotency_key": "memory-security-1",
        "category": "DispatchMemory",
        "fact_kind": "ATTRIBUTE",
        "subject_type": "Vehicle",
        "subject_id": "vehicle-001",
        "predicate": "STATUS",
        "value_json": {"status": "BROKEN"},
        "confidence": "0.9",
        "incoming_at": datetime.now(UTC).isoformat(),
        "source_type": "operator",
        "source_id": "console",
        "human_confirmed": True,
        "reason": "inspection",
        "targets": ["GRAPH"],
        "evidence_text": "inspected",
    }


def test_memory_mutation_requires_permission() -> None:
    service = MemoryService()
    app = create_app(shared_memory_service=service, **auth(Role.DISPATCHER))

    response = TestClient(app).post("/api/v1/memory/mutations", json=memory_payload(), headers=headers())

    assert response.status_code == 403
    assert response.json()["code"] == "AUTHORIZATION_DENIED"
    assert service.commands == []


def test_operator_identity_from_principal() -> None:
    service = MemoryService()
    app = create_app(shared_memory_service=service, **auth(Role.SUPERVISOR))

    response = TestClient(app).post("/api/v1/memory/mutations", json=memory_payload(), headers=headers())

    assert response.status_code == 200
    assert service.commands[0].operator_id == "supervisor-1"


def test_client_cannot_spoof_operator() -> None:
    service = MemoryService()
    app = create_app(shared_memory_service=service, **auth(Role.SUPERVISOR))
    payload = {**memory_payload(), "operator_id": "admin-spoof"}

    response = TestClient(app).post("/api/v1/memory/mutations", json=payload, headers=headers())

    assert response.status_code == 422
    assert service.commands == []


class ObservabilityService:
    async def summary(self, window):
        raise AssertionError("unauthorized monitoring reached the service")


def test_monitor_requires_permission() -> None:
    app = create_app(observability_service=ObservabilityService(), **auth(Role.DISPATCHER))

    response = TestClient(app).get("/api/v1/observability/summary", headers=headers())

    assert response.status_code == 403
    assert response.json()["code"] == "AUTHORIZATION_DENIED"


class AuditRepository:
    def list_recent(self, *, limit: int):
        raise AssertionError("unauthorized audit read reached the repository")


def test_audit_requires_permission() -> None:
    dependencies = auth(Role.DISPATCHER)
    dependencies["security_audit_repository"] = AuditRepository()
    app = create_app(**dependencies)

    response = TestClient(app).get("/api/v1/security/audit", headers=headers())

    assert response.status_code == 403
    assert response.json()["code"] == "AUTHORIZATION_DENIED"


class WorkspaceReadService:
    def __init__(self) -> None:
        self.calls = 0

    def _forbidden(self):
        self.calls += 1
        raise AssertionError("unauthorized workspace read reached the service")

    def get_overview(self):
        return self._forbidden()

    def list_orders(self, **kwargs):
        return self._forbidden()

    def list_anomalies(self, **kwargs):
        return self._forbidden()

    def list_reviews(self, **kwargs):
        return self._forbidden()

    def list_my_tasks(self, **kwargs):
        return self._forbidden()

    def list_runtime_threads(self, **kwargs):
        return self._forbidden()

    async def list_vector_memories(self, **kwargs):
        return self._forbidden()


def test_workspace_routes_require_their_exact_permissions() -> None:
    routes = (
        ("/api/v1/workspace/overview", Role.SUPERVISOR),
        ("/api/v1/orders", Role.OPERATOR),
        ("/api/v1/anomalies", Role.OPERATOR),
        ("/api/v1/reviews", Role.DISPATCHER),
        ("/api/v1/my/tasks", Role.OPERATOR),
        ("/api/v1/runtime/threads", Role.DISPATCHER),
        ("/api/v1/memory/records", Role.OPERATOR),
    )

    for path, role in routes:
        service = WorkspaceReadService()
        app = create_app(workspace_read_service=service, **auth(role))
        response = TestClient(app).get(path, headers=headers())

        assert response.status_code == 403
        assert response.json()["code"] == "AUTHORIZATION_DENIED"
        assert service.calls == 0
