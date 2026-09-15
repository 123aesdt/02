from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymysql.err import OperationalError as PyMySQLOperationalError
from sqlalchemy.exc import OperationalError

from app.api.v1.workspace_read_schemas import OverviewResponse
from app.main import create_app
from app.security.models import AuthenticatedPrincipal, AuthMethod, Role
from app.security.permissions import ROLE_PERMISSION_MATRIX
from app.security.rate_limit import RateLimitDecision
from app.workspace_reads.models import (
    AnomalyListItem,
    DomainCounts,
    MyTaskListItem,
    MyTaskPage,
    MyTaskSummary,
    OrderListItem,
    Page,
    ReviewListItem,
    RuntimeThreadListItem,
    VectorMemoryListItem,
    VectorMemoryPage,
)
from app.workspace_reads.qdrant_repository import (
    InvalidVectorMemoryCursor as AdapterInvalidVectorMemoryCursor,
)
from app.workspace_reads.qdrant_repository import (
    VectorMemoryReadUnavailable as AdapterVectorMemoryReadUnavailable,
)
from app.workspace_reads.service import (
    InvalidWorkspaceCursor,
    WorkspaceOverview,
    WorkspaceReadService,
    WorkspaceReadUnavailable,
)


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


class AllowLimiter:
    async def admit(self, subject_id, operation):
        return RateLimitDecision(True, 100, 0, 1)


class SecurityRepository:
    def append(self, event) -> None:
        return None

    def list_recent(self, *, limit: int):
        return []


def auth(role: Role) -> dict[str, object]:
    return {
        "authentication_provider": PrincipalProvider(role),
        "revocation_store": Revocations(),
        "rate_limiter": AllowLimiter(),
        "security_audit_repository": SecurityRepository(),
    }


def headers() -> dict[str, str]:
    return {"Authorization": "Bearer signed-test-token"}


class StubWorkspaceReadService:
    def __init__(self) -> None:
        created_at = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
        self.orders = Page(
            items=(
                OrderListItem(
                    1,
                    "ORDER-1",
                    "PENDING",
                    "driver-1",
                    "vehicle-1",
                    "route-1",
                    "A",
                    "B",
                    created_at,
                    created_at,
                    1,
                    "TASK-1",
                ),
            ),
            total=1,
            next_cursor=None,
        )
        self.anomalies = Page(
            items=(
                AnomalyListItem(
                    2,
                    "ANOM-1",
                    "ORDER-1",
                    "driver-1",
                    "vehicle-1",
                    "route-1",
                    "TASK-1",
                    "ROAD",
                    "HIGH",
                    "road closed",
                    "OPEN",
                    created_at,
                ),
            ),
            total=1,
            next_cursor=None,
        )
        self.reviews = Page(
            items=(ReviewListItem(3, "TASK-1", "ORDER-1", "HIGH", "road closed", "vehicle-1", "route-1", "route-2", "REVIEW_REQUIRED", created_at),),
            total=1,
            next_cursor=None,
        )
        self.runtime_threads = Page(
            items=(RuntimeThreadListItem(4, "thread-1", "TASK-1", "RUNNING", "routing", "dispatch", 2, 3, "worker-1", None, created_at),),
            total=1,
            next_cursor=None,
        )
        self.my_tasks = MyTaskPage(
            items=(
                MyTaskListItem(
                    5,
                    "TASK-MINE-1",
                    "ORDER-1",
                    "HIGH",
                    "道路封闭",
                    "vehicle-1",
                    "route-1",
                    "route-2",
                    "APPROVED",
                    created_at,
                    created_at,
                ),
            ),
            summary=MyTaskSummary(total=1, ready=1, waiting=0, active=0, ended=0),
            total=1,
            next_cursor=None,
            provenance="DEMO",
        )
        self.vector_memories = VectorMemoryPage(
            items=(VectorMemoryListItem("memory-1", "driver-1", "route-1", "ROAD", "reroute", created_at, "ACTIVE"),),
            total=1,
            next_cursor=None,
            vector_dimension=128,
        )
        self.review_calls = 0
        self.my_task_call = None

    def get_overview(self):
        return WorkspaceOverview(orders=1, anomalies=1, reviews=1, runtime_threads=1, provenance="LIVE")

    def list_orders(self, *, limit: int, cursor: str | None, query: str | None, status: str | None):
        return self.orders

    def list_anomalies(self, *, limit: int, cursor: str | None, query: str | None, risk: str | None, status: str | None):
        return self.anomalies

    def list_reviews(self, *, limit: int, cursor: str | None):
        self.review_calls += 1
        return self.reviews

    def list_my_tasks(self, *, subject_id: str, limit: int, cursor: str | None, state: str | None):
        self.my_task_call = {
            "subject_id": subject_id,
            "limit": limit,
            "cursor": cursor,
            "state": state,
        }
        return self.my_tasks

    def list_runtime_threads(self, *, limit: int, cursor: str | None, status: str | None):
        return self.runtime_threads

    async def list_vector_memories(self, *, limit: int, cursor: str | None):
        return self.vector_memories


def ready_service() -> StubWorkspaceReadService:
    return StubWorkspaceReadService()


def test_workspace_overview_returns_only_real_domain_counts() -> None:
    app = create_app(workspace_read_service=ready_service(), **auth(Role.ADMIN))
    response = TestClient(app).get("/api/v1/workspace/overview", headers=headers())
    assert response.status_code == 200
    assert response.json() == {"orders": 1, "anomalies": 1, "reviews": 1, "runtime_threads": 1, "provenance": "LIVE"}


def test_overview_response_rejects_missing_provenance() -> None:
    class CountsWithoutProvenance:
        orders = 1
        anomalies = 1
        reviews = 1
        runtime_threads = 1

    with pytest.raises(ValidationError):
        OverviewResponse.model_validate(CountsWithoutProvenance(), from_attributes=True)


def test_order_list_returns_safe_page() -> None:
    app = create_app(workspace_read_service=ready_service(), **auth(Role.DISPATCHER))
    response = TestClient(app).get("/api/v1/orders?query=ORDER&status=PENDING", headers=headers())
    assert response.status_code == 200
    assert response.json()["items"][0] == {
        "row_id": 1,
        "order_no": "ORDER-1",
        "status": "PENDING",
        "driver_id": "driver-1",
        "vehicle_id": "vehicle-1",
        "route_id": "route-1",
        "origin": "A",
        "destination": "B",
        "created_at": "2026-08-29T08:00:00Z",
        "updated_at": "2026-08-29T08:00:00Z",
        "anomaly_count": 1,
        "latest_task_id": "TASK-1",
    }


def test_anomaly_list_returns_safe_page() -> None:
    app = create_app(workspace_read_service=ready_service(), **auth(Role.DISPATCHER))
    response = TestClient(app).get("/api/v1/anomalies?query=ANOM&risk=HIGH&status=OPEN", headers=headers())
    assert response.status_code == 200
    assert response.json()["items"][0] == {
        "row_id": 2,
        "anomaly_no": "ANOM-1",
        "order_no": "ORDER-1",
        "driver_id": "driver-1",
        "vehicle_id": "vehicle-1",
        "route_id": "route-1",
        "latest_task_id": "TASK-1",
        "anomaly_type": "ROAD",
        "risk": "HIGH",
        "description": "road closed",
        "status": "OPEN",
        "reported_at": "2026-08-29T08:00:00Z",
    }


def test_review_list_returns_safe_page() -> None:
    app = create_app(workspace_read_service=ready_service(), **auth(Role.SUPERVISOR))
    response = TestClient(app).get("/api/v1/reviews", headers=headers())
    assert response.status_code == 200
    assert response.json()["items"][0]["task_id"] == "TASK-1"


def test_my_tasks_uses_authenticated_subject_and_returns_summary() -> None:
    service = ready_service()
    app = create_app(workspace_read_service=service, **auth(Role.DISPATCHER))

    response = TestClient(app).get(
        "/api/v1/my/tasks?limit=5&state=READY",
        headers=headers(),
    )

    assert response.status_code == 200
    assert service.my_task_call == {
        "subject_id": "dispatcher-1",
        "limit": 5,
        "cursor": None,
        "state": "READY",
    }
    assert response.json() == {
        "items": [
            {
                "row_id": 5,
                "task_id": "TASK-MINE-1",
                "order_no": "ORDER-1",
                "risk": "HIGH",
                "description": "道路封闭",
                "vehicle_id": "vehicle-1",
                "original_route_id": "route-1",
                "suggested_route_id": "route-2",
                    "status": "APPROVED",
                    "created_at": "2026-08-29T08:00:00Z",
                    "updated_at": "2026-08-29T08:00:00Z",
                    "origin": None,
                    "destination": None,
                    "publication_status": "PENDING",
                    "published_at": None,
                    "route_instruction": None,
                    "can_report_anomaly": False,
                }
        ],
        "summary": {"total": 1, "ready": 1, "waiting": 0, "active": 0, "ended": 0},
        "total": 1,
        "next_cursor": None,
        "provenance": "DEMO",
    }


def test_my_tasks_unavailable_uses_workspace_503_contract() -> None:
    service = ready_service()

    def unavailable(**kwargs):
        raise WorkspaceReadUnavailable("database unavailable")

    service.list_my_tasks = unavailable
    app = create_app(workspace_read_service=service, **auth(Role.DISPATCHER))

    response = TestClient(app).get("/api/v1/my/tasks", headers=headers())

    assert response.status_code == 503
    assert response.json()["code"] == "WORKSPACE_READ_UNAVAILABLE"


def test_runtime_list_never_serializes_checkpoint_payload() -> None:
    app = create_app(workspace_read_service=ready_service(), **auth(Role.OPERATOR))
    body = TestClient(app).get("/api/v1/runtime/threads?status=RUNNING", headers=headers()).json()
    assert body["items"][0]["task_id"] == "TASK-1"
    assert "checkpoint" not in body["items"][0]
    assert "state" not in body["items"][0]


def test_vector_memory_list_never_serializes_vector_or_metadata() -> None:
    app = create_app(workspace_read_service=ready_service(), **auth(Role.DISPATCHER))
    response = TestClient(app).get("/api/v1/memory/records", headers=headers())
    assert response.status_code == 200
    body = response.json()
    assert body["vector_dimension"] == 128
    assert "vector" not in body["items"][0]
    assert "metadata" not in body["items"][0]


def test_list_limit_bounds_are_validated() -> None:
    app = create_app(workspace_read_service=ready_service(), **auth(Role.DISPATCHER))
    client = TestClient(app)
    assert client.get("/api/v1/orders?limit=0", headers=headers()).status_code == 422
    assert client.get("/api/v1/orders?limit=101", headers=headers()).status_code == 422


def test_malformed_mysql_cursor_is_a_client_error() -> None:
    service = ready_service()
    def invalid_cursor(*, limit: int, cursor: str | None, query: str | None, status: str | None):
        raise InvalidWorkspaceCursor("workspace cursor must be a numeric string")
    service.list_orders = invalid_cursor
    app = create_app(workspace_read_service=service, **auth(Role.DISPATCHER))
    response = TestClient(app).get("/api/v1/orders?cursor=bad-cursor", headers=headers())
    assert response.status_code == 422


def test_vector_memory_unavailability_is_bounded() -> None:
    service = WorkspaceReadService(EmptyWorkspaceRepository(), UnavailableVectorRepository())
    response = TestClient(create_app(workspace_read_service=service, **auth(Role.DISPATCHER))).get("/api/v1/memory/records", headers=headers())
    assert response.status_code == 503
    assert response.json()["code"] == "VECTOR_MEMORY_UNAVAILABLE"
    assert "provider URL" not in response.text


def test_empty_page_is_a_successful_live_response() -> None:
    service = ready_service()
    service.orders = Page(items=(), total=0, next_cursor=None)
    response = TestClient(create_app(workspace_read_service=service, **auth(Role.DISPATCHER))).get("/api/v1/orders", headers=headers())
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "next_cursor": None, "provenance": "LIVE"}


def test_invalid_vector_cursor_is_a_client_error() -> None:
    service = WorkspaceReadService(EmptyWorkspaceRepository(), InvalidCursorVectorRepository())
    response = TestClient(create_app(workspace_read_service=service, **auth(Role.DISPATCHER))).get("/api/v1/memory/records?cursor=bad", headers=headers())
    assert response.status_code == 422


class EmptyWorkspaceRepository:
    def count_domains(self):
        return DomainCounts(orders=0, anomalies=0, reviews=0, runtime_threads=0, provenance="LIVE")


class UnavailableVectorRepository:
    async def list_records(self, *, limit: int, cursor: str | None):
        raise AdapterVectorMemoryReadUnavailable("provider URL and authorization must not leak")


class InvalidCursorVectorRepository:
    async def list_records(self, *, limit: int, cursor: str | None):
        raise AdapterInvalidVectorMemoryCursor("invalid vector cursor contains secret")


def test_connection_invalidated_mysql_error_becomes_workspace_unavailable() -> None:
    error = OperationalError(None, None, ConnectionError("connection lost"), connection_invalidated=True)
    repository = FailingWorkspaceRepository(error)

    with pytest.raises(WorkspaceReadUnavailable):
        WorkspaceReadService(repository, EmptyVectorRepository()).get_overview()


def test_non_connection_operational_error_propagates_unchanged() -> None:
    error = OperationalError(None, None, RuntimeError("bad SQL"))
    repository = FailingWorkspaceRepository(error)

    with pytest.raises(OperationalError) as raised:
        WorkspaceReadService(repository, EmptyVectorRepository()).get_overview()

    assert raised.value is error


@pytest.mark.parametrize("code", [2002, 2003, 2006, 2013])
def test_pymysql_connection_operational_codes_become_workspace_unavailable(code: int) -> None:
    error = OperationalError(
        None,
        None,
        PyMySQLOperationalError(code, "database connection failed"),
    )

    with pytest.raises(WorkspaceReadUnavailable):
        WorkspaceReadService(FailingWorkspaceRepository(error), EmptyVectorRepository()).get_overview()


def test_sqlstate_connection_class_becomes_workspace_unavailable() -> None:
    error = OperationalError(
        None,
        None,
        PyMySQLOperationalError("08S01", "communication link failure"),
    )

    with pytest.raises(WorkspaceReadUnavailable):
        WorkspaceReadService(FailingWorkspaceRepository(error), EmptyVectorRepository()).get_overview()


def test_pymysql_sql_error_propagates_unchanged() -> None:
    error = OperationalError(
        None,
        None,
        PyMySQLOperationalError(1064, "syntax error"),
    )

    with pytest.raises(OperationalError) as raised:
        WorkspaceReadService(FailingWorkspaceRepository(error), EmptyVectorRepository()).get_overview()

    assert raised.value is error


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/orders",
        "/api/v1/anomalies",
        "/api/v1/reviews",
        "/api/v1/my/tasks",
        "/api/v1/runtime/threads",
    ],
)
@pytest.mark.parametrize("cursor", ["-1", "not-numeric", "9" * 65])
def test_mysql_list_routes_reject_invalid_cursors_before_calling_the_service(
    path: str,
    cursor: str,
) -> None:
    app = create_app(workspace_read_service=ready_service(), **auth(Role.ADMIN))

    response = TestClient(app).get(path, params={"cursor": cursor}, headers=headers())

    assert response.status_code == 422


def test_vector_memory_route_rejects_an_oversized_cursor() -> None:
    app = create_app(workspace_read_service=ready_service(), **auth(Role.ADMIN))

    response = TestClient(app).get(
        "/api/v1/memory/records",
        params={"cursor": "a" * 513},
        headers=headers(),
    )

    assert response.status_code == 422


@pytest.mark.parametrize("path", ["/api/v1/orders", "/api/v1/anomalies"])
def test_search_query_rejects_values_longer_than_the_read_contract(path: str) -> None:
    app = create_app(workspace_read_service=ready_service(), **auth(Role.ADMIN))

    response = TestClient(app).get(path, params={"query": "x" * 129}, headers=headers())

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("path", "parameter"),
    [
        ("/api/v1/orders", "status"),
        ("/api/v1/anomalies", "status"),
        ("/api/v1/anomalies", "risk"),
        ("/api/v1/runtime/threads", "status"),
        ("/api/v1/my/tasks", "state"),
    ],
)
def test_list_filters_reject_values_outside_the_published_enums(
    path: str,
    parameter: str,
) -> None:
    app = create_app(workspace_read_service=ready_service(), **auth(Role.ADMIN))

    response = TestClient(app).get(path, params={parameter: "NOT_A_REAL_VALUE"}, headers=headers())

    assert response.status_code == 422


class FailingWorkspaceRepository:
    def __init__(self, error: OperationalError) -> None:
        self._error = error

    def count_domains(self):
        raise self._error


class EmptyVectorRepository:
    async def list_records(self, *, limit: int, cursor: str | None):
        raise AssertionError("vector repository should not be used")
