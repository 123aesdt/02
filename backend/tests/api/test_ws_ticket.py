from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from security_support import authorize_app
from starlette.websockets import WebSocketDisconnect

from app.api.v1.task_events import router as task_events_router
from app.api.v1.task_events import task_events
from app.api.v1.ws_tickets import router as ws_ticket_router
from app.security.permissions import Role
from app.security.rate_limit import OperationClass, RateLimitDecision
from app.security.ws_ticket import ConsumedWsTicket, IssuedWsTicket, WsTicketRejected
from app.services.dispatch_task_api_service import TaskAccessForbiddenError


class DispatchService:
    def require_read_access(self, task_id, *, subject_id, can_read_all):
        if not can_read_all and task_id == "TASK-other":
            raise TaskAccessForbiddenError

    def status(self, task_id):
        if task_id == "TASK-missing":
            from app.services.dispatch_task_api_service import TaskNotFoundError

            raise TaskNotFoundError
        return {"status": "PENDING", "ready": False, "requires_manual_review": False}


class TicketService:
    def __init__(self, *, reject: str | None = None) -> None:
        self.reject = reject
        self.issued = []
        self.consumed = []

    async def issue(self, principal, **scope):
        self.issued.append((principal.subject_id, scope))
        return IssuedWsTicket("t" * 43, scope["target_type"], scope["target_id"], datetime.now(UTC) + timedelta(seconds=45))

    async def consume(self, ticket, **scope):
        self.consumed.append((ticket, scope))
        if self.reject:
            raise WsTicketRejected(self.reject)
        return ConsumedWsTicket(
            "test-admin",
            scope["target_type"],
            scope["target_id"],
            scope["required_permission"],
            datetime.now(UTC),
            datetime.now(UTC) + timedelta(seconds=45),
        )


class Broker:
    async def history(self, task_id, *, after_event_id=None):
        return []

    async def subscribe(self, task_id, last_event_id=None):
        raise RuntimeError("stop after authenticated snapshot")

    async def unsubscribe(self, subscription):
        return None


class Metrics:
    def increment(self, name, labels=None):
        return None

    def adjust_gauge(self, name, amount, labels=None):
        return None


class Admission:
    def __init__(self) -> None:
        self.operations = []

    async def check(self, principal, operation):
        self.operations.append(operation)
        return RateLimitDecision(True, 9, 0, 1)


def app(ticket_service: TicketService, role: Role = Role.ADMIN) -> tuple[FastAPI, Admission]:
    application = authorize_app(FastAPI(), role)
    admission = Admission()
    application.state.rate_limit_admission = admission
    application.state.ws_ticket_service = ticket_service
    application.state.dispatch_task_api_service = DispatchService()
    application.state.task_event_broker = Broker()
    application.state.metrics_recorder = Metrics()
    application.include_router(ws_ticket_router)
    application.include_router(task_events_router)
    return application, admission


def test_ws_ticket_issuance() -> None:
    tickets = TicketService()
    application, admission = app(tickets)

    response = TestClient(application).post(
        "/api/v1/ws-tickets",
        json={"target_type": "task", "target_id": "TASK-1"},
    )

    assert response.status_code == 201
    assert response.json()["ticket"] == "t" * 43
    assert response.json()["expires_in_seconds"] == 45
    assert tickets.issued[0][0] == "test-admin"
    assert admission.operations == [OperationClass.WS_TICKET]


def test_ws_ticket_missing_target_is_safe_404() -> None:
    application, _ = app(TicketService())
    response = TestClient(application).post(
        "/api/v1/ws-tickets",
        json={"target_type": "task", "target_id": "TASK-missing"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "TASK_NOT_FOUND"


def test_delivery_employee_cannot_subscribe_to_another_employees_task() -> None:
    tickets = TicketService()
    application, _ = app(tickets, Role.EMPLOYEE)

    response = TestClient(application).post(
        "/api/v1/ws-tickets",
        json={"target_type": "task", "target_id": "TASK-other"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "TASK_ACCESS_FORBIDDEN"
    assert tickets.issued == []


def test_websocket_requires_ticket() -> None:
    application, _ = app(TicketService())
    with TestClient(application).websocket_connect("/api/v1/ws/tasks/TASK-1") as socket:
        with pytest.raises(WebSocketDisconnect) as captured:
            socket.receive_json()
    assert captured.value.code == 4401


@pytest.mark.parametrize(
    ("rejection", "close_code"),
    [
        ("WS_TICKET_INVALID", 4401),
        ("WS_TICKET_WRONG_SCOPE", 4403),
        ("WS_TICKET_PERMISSION_DENIED", 4403),
        ("WS_TICKET_REPLAYED_OR_EXPIRED", 4408),
    ],
)
def test_websocket_ticket_rejection_codes(rejection: str, close_code: int) -> None:
    application, _ = app(TicketService(reject=rejection))
    with TestClient(application).websocket_connect(
        f"/api/v1/ws/tasks/TASK-1?ticket={'t' * 43}"
    ) as socket:
        with pytest.raises(WebSocketDisconnect) as captured:
            socket.receive_json()
    assert captured.value.code == close_code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ticket", "rejection", "close_code"),
    [
        (None, None, 4401),
        ("t" * 43, "WS_TICKET_WRONG_SCOPE", 4403),
        ("t" * 43, "WS_TICKET_REPLAYED_OR_EXPIRED", 4408),
    ],
)
async def test_websocket_security_close_code_is_visible_to_real_clients(
    ticket: str | None,
    rejection: str | None,
    close_code: int,
) -> None:
    calls: list[str] = []

    class Socket:
        query_params = {} if ticket is None else {"ticket": ticket}
        url = SimpleNamespace(path="/api/v1/ws/tasks/TASK-1")
        app = SimpleNamespace(
            state=SimpleNamespace(
                ws_ticket_service=TicketService(reject=rejection),
                dispatch_task_api_service=object(),
                task_event_broker=object(),
                metrics_recorder=None,
                security_audit_recorder=None,
            )
        )

        async def accept(self) -> None:
            calls.append("accept")

        async def close(self, *, code: int) -> None:
            calls.append(f"close:{code}")

    await task_events(Socket(), "TASK-1")

    assert calls == ["accept", f"close:{close_code}"]
