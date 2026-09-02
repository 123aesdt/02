from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


def _app_with_cors_origins(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:5174")
    get_settings.cache_clear()
    assert get_settings().cors_allowed_origins_list == ["http://localhost:5173", "http://localhost:5174"]
    return create_app()


def test_cors_allows_configured_frontend_origin(monkeypatch):
    app = _app_with_cors_origins(monkeypatch)

    response = TestClient(app).get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    get_settings.cache_clear()


def test_cors_preflight_dispatch_task(monkeypatch):
    app = _app_with_cors_origins(monkeypatch)

    response = TestClient(app).options(
        "/api/v1/dispatch-tasks",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in response.headers["access-control-allow-methods"]
    get_settings.cache_clear()


def test_cors_rejects_unconfigured_origin(monkeypatch):
    app = _app_with_cors_origins(monkeypatch)

    response = TestClient(app).get("/health", headers={"Origin": "http://evil.example"})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") != "http://evil.example"
    get_settings.cache_clear()
