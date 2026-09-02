from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from security_support import authorize_app

from app.api.v1.memory_mutations import router
from app.core.config import get_settings
from app.main import create_app
from app.security.permissions import Role
from app.shared_memory.models import (
    MemoryMutationResult,
    MutationDecision,
    MutationStatus,
    ProjectionStatus,
)
from app.shared_memory.policy import MemoryVersionConflict
from app.shared_memory.service import MemoryMutationBusy
from app.shared_memory.sqlalchemy_repository import MemoryIdempotencyConflict

MUTATION_ID = "00000000-0000-0000-0000-000000000008"
FACT_KEY = "smf_" + "a" * 64


class StubMemoryService:
    def __init__(self, result=None, error=None) -> None:
        self.result = result or mutation_result()
        self.error = error

    async def mutate(self, command):
        if self.error:
            raise self.error
        return self.result

    def get_mutation_result(self, mutation_id):
        if mutation_id != MUTATION_ID:
            raise LookupError(mutation_id)
        return self.result

    def get_fact_detail(self, fact_key):
        if fact_key != FACT_KEY:
            raise LookupError(fact_key)
        return {
            "fact_key": FACT_KEY,
            "category": "DispatchMemory",
            "fact_kind": "ATTRIBUTE",
            "subject_type": "Vehicle",
            "subject_id": "vehicle-a",
            "predicate": "STATUS",
            "object_type": None,
            "object_id": None,
            "version": 8,
            "confidence": "0.9000",
            "status": "ACTIVE",
            "expires_at": None,
            "vector_memory_id": "memory-vehicle-a-status",
            "graph_fact_key": "Vehicle:vehicle-a:STATUS",
            "last_mutation_id": MUTATION_ID,
            "updated_at": datetime(2026, 8, 27, 1, 1, tzinfo=UTC).isoformat(),
            "value_json": {"status": "Broken"},
            "mutations": [
                {
                    "mutation_id": MUTATION_ID,
                    "decision": "REPLACE",
                    "status": "APPLIED",
                    "source_type": "operator",
                    "source_id": "ops-console",
                    "operator_id": "operator-1",
                    "incoming_confidence": "0.9000",
                    "completed_at": datetime(2026, 8, 27, 1, 1, tzinfo=UTC).isoformat(),
                }
            ],
            "evidence": [],
        }


def mutation_result(status=MutationStatus.APPLIED):
    return MemoryMutationResult(
        mutation_id=MUTATION_ID,
        fact_key=FACT_KEY,
        decision=MutationDecision.REPLACE,
        status=status,
        before_version=7,
        after_version=8,
        vector_status=ProjectionStatus.ACTIVE,
        graph_status=ProjectionStatus.ACTIVE if status is MutationStatus.APPLIED else ProjectionStatus.FAILED,
        projection_incomplete=status is MutationStatus.PARTIAL,
    )


def client(service, role: Role = Role.ADMIN) -> TestClient:
    app = authorize_app(FastAPI(), role)
    app.state.shared_memory_service = service
    app.include_router(router)
    return TestClient(app)


def payload() -> dict[str, object]:
    return {
        "idempotency_key": "api-idem-1",
        "category": "DispatchMemory",
        "fact_kind": "ATTRIBUTE",
        "subject_type": "Vehicle",
        "subject_id": "vehicle-a",
        "predicate": "STATUS",
        "value_json": {"status": "Broken"},
        "expected_version": 7,
        "confidence": "0.9000",
        "incoming_at": datetime(2026, 8, 27, 1, 0, tzinfo=UTC).isoformat(),
        "source_type": "operator",
        "source_id": "ops-console",
        "human_confirmed": True,
        "reason": "inspection",
        "evidence_text": "vehicle inspected",
        "evidence_observed_at": datetime(2026, 8, 27, 1, 0, tzinfo=UTC).isoformat(),
        "targets": ["GRAPH"],
    }


def test_memory_mutation_api_returns_typed_applied_response() -> None:
    response = client(StubMemoryService()).post("/api/v1/memory/mutations", json=payload())

    assert response.status_code == 200
    assert response.json()["status"] == "APPLIED"
    assert response.json()["projection_incomplete"] is False


def test_memory_mutation_api_returns_202_for_partial() -> None:
    response = client(StubMemoryService(mutation_result(MutationStatus.PARTIAL))).post(
        "/api/v1/memory/mutations", json=payload()
    )

    assert response.status_code == 202
    assert response.json()["projection_incomplete"] is True


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (MemoryVersionConflict(FACT_KEY, 7, 8), "MEMORY_VERSION_CONFLICT"),
        (MemoryIdempotencyConflict("idem"), "MEMORY_IDEMPOTENCY_CONFLICT"),
        (MemoryMutationBusy(FACT_KEY), "MEMORY_MUTATION_BUSY"),
    ],
)
def test_memory_mutation_api_distinguishes_409_conflicts(error, code) -> None:
    response = client(StubMemoryService(error=error)).post(
        "/api/v1/memory/mutations", json=payload()
    )

    assert response.status_code == 409
    assert response.json()["code"] == code


def test_memory_management_get_endpoints_are_bounded() -> None:
    api = client(StubMemoryService())

    mutation = api.get(f"/api/v1/memory/mutations/{MUTATION_ID}")
    fact = api.get(f"/api/v1/memory/facts/{FACT_KEY}")

    assert mutation.status_code == fact.status_code == 200
    assert mutation.json()["after_version"] == 8
    assert fact.json()["version"] == 8
    assert fact.json()["category"] == "DispatchMemory"
    assert fact.json()["subject_id"] == "vehicle-a"
    assert fact.json()["vector_memory_id"] == "memory-vehicle-a-status"
    assert fact.json()["graph_fact_key"] == "Vehicle:vehicle-a:STATUS"
    assert fact.json()["last_mutation_id"] == MUTATION_ID
    assert fact.json()["mutations"][0]["decision"] == "REPLACE"
    assert fact.json()["mutations"][0]["operator_id"] == "operator-1"
    assert fact.json()["mutations"][0]["incoming_confidence"] == "0.9000"


def test_memory_read_without_audit_permission_redacts_actor_and_evidence() -> None:
    response = client(StubMemoryService(), Role.DISPATCHER).get(f"/api/v1/memory/facts/{FACT_KEY}")

    assert response.status_code == 200
    serialized = response.text
    assert "operator_id" not in serialized
    assert "source_id" not in serialized
    assert response.json()["evidence"] == []


def test_memory_management_api_is_not_mounted_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MEMORY_MUTATION_API_ENABLED", "false")
    get_settings.cache_clear()

    response = TestClient(create_app()).post("/api/v1/memory/mutations", json=payload())

    assert response.status_code == 404
    get_settings.cache_clear()
