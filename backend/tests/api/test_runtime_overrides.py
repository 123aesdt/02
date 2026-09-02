from dataclasses import replace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from security_support import authorize_app

from app.api.v1.runtime_overrides import router
from app.main import create_app
from app.runtime_overrides.models import RuntimeOverrideDecision, RuntimeOverrideStatus, StoredRuntimeOverride
from app.runtime_overrides.query_models import (
    RuntimeInterventionContext,
    RuntimeInterventionEligibility,
    RuntimeInterventionTarget,
)
from app.security.permissions import Role
from tests.runtime_overrides.factories import NOW


class Service:
    def __init__(self, result: StoredRuntimeOverride | None = None) -> None:
        self.applied = StoredRuntimeOverride(
            override_id="00000000-0000-0000-0000-000000000001",
            thread_id="thread-1",
            task_id="task-1",
            idempotency_key="key-1",
            payload_fingerprint="f" * 64,
            operator_id="operator-from-auth",
            operator_role="dispatcher",
            status=RuntimeOverrideStatus.APPLIED,
            decision=RuntimeOverrideDecision.ALLOWED,
            expected_version=7,
            expected_next_node="capacity",
            before_state_version=7,
            after_state_version=8,
            entity_type="Vehicle",
            entity_id="vehicle-001",
            field="status",
            old_value="NORMAL",
            new_value="BROKEN",
            reason="breakdown",
            source_checkpoint_id="c7",
            result_checkpoint_id="c8",
            event_status="PUBLISHED",
            error_code=None,
            error_summary=None,
            requested_at=NOW,
            started_at=NOW,
            completed_at=NOW,
        )
        if result is not None:
            self.applied = result

    async def apply(self, thread_id, request, principal=None):
        assert thread_id == "thread-1"
        assert not hasattr(request, "operator_id")
        assert principal is not None
        return self.applied

    def get(self, override_id, principal):
        assert principal is not None
        assert override_id == self.applied.override_id
        return self.applied


class QueryService:
    def __init__(self, item: StoredRuntimeOverride) -> None:
        self.item = item

    async def get_intervention_context(self, thread_id: str, principal):
        assert principal is not None
        return RuntimeInterventionContext(
            thread_id=thread_id,
            task_id=self.item.task_id,
            runtime_status="STABLE",
            state_version=7,
            current_node="environment",
            next_node="capacity",
            canonical_checkpoint_id="c7",
            checkpoint_available=True,
            eligibility=RuntimeInterventionEligibility.ELIGIBLE,
            eligibility_reason_code=None,
            can_override=True,
            target=RuntimeInterventionTarget(
                "Vehicle",
                "vehicle-001",
                "冷链车A",
                "status",
                "NORMAL",
                ("BROKEN", "UNAVAILABLE", "MAINTENANCE"),
            ),
            observed_at=NOW,
        )

    def get(self, override_id: str, principal):
        assert principal is not None
        assert override_id == self.item.override_id
        return self.item

    def list_by_thread(self, thread_id: str, principal, *, limit: int):
        assert principal is not None
        assert (thread_id, limit) == (self.item.thread_id, 5)
        return [self.item]


def app(service: Service | None = None, query: QueryService | None = None, *, role: Role = Role.ADMIN) -> FastAPI:
    value = authorize_app(FastAPI(), role)
    command_service = service or Service()
    value.state.runtime_override_service = command_service
    value.state.runtime_override_query_service = query or QueryService(command_service.applied)
    value.include_router(router)
    return value


def payload() -> dict[str, object]:
    return {
        "idempotency_key": "key-1",
        "entity_type": "Vehicle",
        "entity_id": "vehicle-001",
        "field": "status",
        "old_value": "NORMAL",
        "new_value": "BROKEN",
        "reason": "breakdown",
        "expected_version": 7,
        "expected_next_node": "capacity",
    }


def test_runtime_override_api() -> None:
    response = TestClient(app()).post("/api/v1/runtime/threads/thread-1/overrides", json=payload())
    assert response.status_code == 200
    assert response.json()["status"] == "APPLIED"
    assert response.json()["after_state_version"] == 8


def test_runtime_override_get_api() -> None:
    service = Service()
    response = TestClient(app(service)).get(f"/api/v1/runtime/overrides/{service.applied.override_id}")
    assert response.status_code == 200
    assert response.json()["operator_id"] == "operator-from-auth"


def test_runtime_intervention_context_api() -> None:
    response = TestClient(app()).get("/api/v1/runtime/threads/thread-1/intervention")

    assert response.status_code == 200
    assert response.json()["eligibility"] == "ELIGIBLE"
    assert response.json()["target"] == {
        "entity_type": "Vehicle",
        "entity_id": "vehicle-001",
        "display_name": "冷链车A",
        "field": "status",
        "current_value": "NORMAL",
        "allowed_new_values": ["BROKEN", "UNAVAILABLE", "MAINTENANCE"],
    }


def test_runtime_override_history_api_is_safe_and_bounded() -> None:
    response = TestClient(app()).get("/api/v1/runtime/threads/thread-1/overrides", params={"limit": 5})

    assert response.status_code == 200
    body = response.json()
    assert body["thread_id"] == "thread-1"
    assert body["items"][0]["reason"] == "breakdown"
    serialized = response.text
    for forbidden in ("idempotency_key", "payload_fingerprint", "operator_permissions", '"state"'):
        assert forbidden not in serialized


def test_runtime_override_read_api_enforces_authorization() -> None:
    command_service = Service()
    client = TestClient(app(command_service, QueryService(command_service.applied), role=Role.DISPATCHER))

    assert client.get("/api/v1/runtime/threads/thread-1/intervention").status_code == 403
    assert client.get("/api/v1/runtime/threads/thread-1/overrides", params={"limit": 5}).status_code == 403
    assert client.get(f"/api/v1/runtime/overrides/{command_service.applied.override_id}").status_code == 403


@pytest.mark.parametrize(
    ("status", "code", "http_status"),
    [
        (RuntimeOverrideStatus.CONFLICT, "RUNTIME_STATE_VERSION_CONFLICT", 409),
        (RuntimeOverrideStatus.CONFLICT, "RUNTIME_OVERRIDE_BUSY", 409),
        (RuntimeOverrideStatus.CONFLICT, "THREAD_NOT_STABLE", 409),
        (RuntimeOverrideStatus.REJECTED, "THREAD_TERMINAL", 409),
        (RuntimeOverrideStatus.REJECTED, "OVERRIDE_FIELD_NOT_ALLOWED", 422),
        (RuntimeOverrideStatus.REJECTED, "OVERRIDE_VALUE_INVALID", 422),
        (RuntimeOverrideStatus.FAILED, "CHECKPOINT_STORE_UNAVAILABLE", 503),
    ],
)
def test_runtime_override_api_maps_domain_errors(status, code, http_status) -> None:
    baseline = Service().applied
    result = replace(baseline, status=status, error_code=code)

    response = TestClient(app(Service(result))).post("/api/v1/runtime/threads/thread-1/overrides", json=payload())

    assert response.status_code == http_status
    assert response.json()["error_code"] == code


def test_runtime_override_api_publishes_non_applied_status_event() -> None:
    class Publisher:
        def __init__(self) -> None:
            self.items = []

        async def publish_status(self, item) -> None:
            self.items.append(item)

    baseline = Service().applied
    result = replace(baseline, status=RuntimeOverrideStatus.CONFLICT, error_code="RUNTIME_STATE_VERSION_CONFLICT")
    application = app(Service(result))
    publisher = Publisher()
    application.state.runtime_override_event_publisher = publisher

    response = TestClient(application).post("/api/v1/runtime/threads/thread-1/overrides", json=payload())

    assert response.status_code == 409
    assert publisher.items == [result]


def test_create_app_wires_explicit_runtime_override_query_service() -> None:
    command_service = Service()
    query_service = QueryService(command_service.applied)

    application = authorize_app(
        create_app(
            runtime_override_service=command_service,
            runtime_override_query_service=query_service,
        )
    )
    response = TestClient(application).get("/api/v1/runtime/threads/thread-1/intervention")

    assert response.status_code == 200
    assert response.json()["eligibility"] == "ELIGIBLE"
