from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from security_support import authorize_app

from app.api.v1.runtime_threads import router
from app.security.permissions import Role


def _detail():
    return {
        "thread_id": "cf:dispatch:TASK-6123456789abcdef0123456789abcde",
        "task_id": "TASK-6123456789abcdef0123456789abcde",
        "status": "STABLE",
        "terminal": False,
        "current_checkpoint_id": "checkpoint-1",
        "state_version": 1,
        "current_node": "intake",
        "next_node": "entity_memory",
        "checkpoint_count": 1,
        "checkpoint_size_bytes": 512,
        "last_event_sequence": 7,
        "worker_consumer": "worker-county-02",
        "checkpoint_available": True,
        "state": {"last_completed_node": "intake"},
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "terminal_at": None,
    }


class _Service:
    async def get_current_by_thread(self, thread_id, principal):
        assert principal is not None
        return _detail()

    async def get_current_by_task(self, task_id, principal):
        assert principal is not None
        return _detail()

    async def list_history(self, thread_id, principal, *, limit):
        assert principal is not None
        return {"thread_id": thread_id, "items": [{"checkpoint_id": "checkpoint-1", "state_version": 1}]}


def _client(service=None, *, role: Role = Role.ADMIN):
    app = authorize_app(FastAPI(), role)
    app.state.runtime_thread_service = service or _Service()
    app.include_router(router)
    return TestClient(app)


def test_thread_read_api():
    response = _client().get("/api/v1/runtime/threads/cf:dispatch:TASK-6123456789abcdef0123456789abcde")

    assert response.status_code == 200
    assert response.json()["current_checkpoint_id"] == "checkpoint-1"
    assert response.json()["checkpoint_available"] is True
    assert response.json()["worker_consumer"] == "worker-county-02"
    assert response.json()["updated_at"] is not None


def test_thread_history_api():
    response = _client().get(
        "/api/v1/runtime/threads/cf:dispatch:TASK-6123456789abcdef0123456789abcde/history",
        params={"limit": 1},
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["checkpoint_id"] == "checkpoint-1"
    assert response.json()["items"][0]["state_version"] == 1


def test_runtime_thread_api_denies_unauthorized_reads():
    response = _client(role=Role.DISPATCHER).get(
        "/api/v1/runtime/threads/cf:dispatch:TASK-6123456789abcdef0123456789abcde"
    )

    assert response.status_code == 403


def test_runtime_thread_api_has_no_mutation_routes():
    client = _client()
    path = "/api/v1/runtime/threads/cf:dispatch:TASK-6123456789abcdef0123456789abcde"

    assert client.post(path).status_code == 405
    assert client.patch(path).status_code == 405
    assert client.delete(path).status_code == 405
