from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from security_support import authorize_app

from app.api.v1.dispatch_tasks import router as dispatch_router
from app.api.v1.memory_mutations import router as memory_router
from app.api.v1.runtime_overrides import router as runtime_router
from app.security.errors import SecurityHttpError
from app.security.rate_limit import OperationClass


class DenyAdmission:
    def __init__(self) -> None:
        self.operations = []

    async def check(self, principal, operation):
        self.operations.append((principal.subject_id, operation))
        raise SecurityHttpError(
            429,
            "RATE_LIMIT_EXCEEDED",
            "The operation rate limit has been exceeded.",
            {"Retry-After": "9"},
        )


class UntouchedService:
    async def submit(self, payload):
        raise AssertionError("rate-limited dispatch reached service")

    async def apply(self, thread_id, request, principal=None):
        raise AssertionError("rate-limited override reached service")

    async def mutate(self, command):
        raise AssertionError("rate-limited mutation reached service")


def client(router, state_name: str) -> tuple[TestClient, DenyAdmission]:
    app = authorize_app(FastAPI())
    admission = DenyAdmission()
    app.state.rate_limit_admission = admission
    setattr(app.state, state_name, UntouchedService())
    if state_name == "runtime_override_service":
        app.state.runtime_override_query_service = object()
    app.include_router(router)
    return TestClient(app), admission


def dispatch_payload() -> dict[str, object]:
    return {
        "order_id": 1,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-001",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "Road is slippery.",
        "idempotency_key": "rate-dispatch-1",
    }


def override_payload() -> dict[str, object]:
    return {
        "idempotency_key": "rate-override-1",
        "entity_type": "Vehicle",
        "entity_id": "vehicle-001",
        "field": "status",
        "old_value": "NORMAL",
        "new_value": "BROKEN",
        "reason": "inspection",
        "expected_version": 7,
        "expected_next_node": "capacity",
    }


def memory_payload() -> dict[str, object]:
    return {
        "idempotency_key": "rate-memory-1",
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
    }


@pytest.mark.parametrize(
    ("router", "state_name", "path", "payload", "operation"),
    [
        (dispatch_router, "dispatch_task_api_service", "/api/v1/dispatch-tasks", dispatch_payload(), OperationClass.DISPATCH_SUBMIT),
        (
            runtime_router,
            "runtime_override_service",
            "/api/v1/runtime/threads/thread-1/overrides",
            override_payload(),
            OperationClass.RUNTIME_OVERRIDE,
        ),
        (memory_router, "shared_memory_service", "/api/v1/memory/mutations", memory_payload(), OperationClass.MEMORY_MUTATION),
    ],
)
def test_rate_limit_dispatch(router, state_name, path, payload, operation) -> None:
    api, admission = client(router, state_name)

    response = api.post(path, json=payload)

    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMIT_EXCEEDED"
    assert response.headers["Retry-After"] == "9"
    assert admission.operations == [("test-admin", operation)]


def test_rate_limit_override() -> None:
    api, admission = client(runtime_router, "runtime_override_service")
    assert api.post("/api/v1/runtime/threads/thread-1/overrides", json=override_payload()).status_code == 429
    assert admission.operations[0][1] is OperationClass.RUNTIME_OVERRIDE


def test_rate_limit_memory_mutation() -> None:
    api, admission = client(memory_router, "shared_memory_service")
    assert api.post("/api/v1/memory/mutations", json=memory_payload()).status_code == 429
    assert admission.operations[0][1] is OperationClass.MEMORY_MUTATION
