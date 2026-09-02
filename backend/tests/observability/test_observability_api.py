from fastapi import FastAPI
from fastapi.testclient import TestClient
from security_support import authorize_app

from app.api.v1.observability import router
from app.observability.models import ObservabilityState, ObservabilitySummary
from app.observability.service import ObservabilityUnavailable
from app.security.permissions import Role


class Service:
    async def summary(self, window: str):
        return ObservabilitySummary(state=ObservabilityState.LIVE, window=window, timestamp="2026-08-28T00:00:00+00:00", metrics={"qps": 3.5})


def client(service, role: Role = Role.SUPERVISOR) -> TestClient:
    app = authorize_app(FastAPI(), role)
    app.state.observability_service = service
    app.include_router(router)
    return TestClient(app)


def test_observability_summary_api() -> None:
    response = client(Service()).get("/api/v1/observability/summary?window=5m")
    assert response.status_code == 200
    assert response.json()["state"] == "LIVE"
    assert response.json()["metrics"]["qps"] == 3.5


def test_observability_api_requires_permission() -> None:
    assert client(Service(), Role.DISPATCHER).get("/api/v1/observability/summary?window=5m").status_code == 403


def test_observability_unavailable_safe() -> None:
    class Down:
        async def summary(self, window: str):
            raise ObservabilityUnavailable

    response = client(Down()).get("/api/v1/observability/summary?window=5m")
    assert response.status_code == 503
    assert response.json() == {"code": "OBSERVABILITY_UNAVAILABLE", "message": "Live monitoring is temporarily unavailable."}
