from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.security.http import JsonBodyLimitMiddleware, SecurityHeadersMiddleware


def test_security_headers() -> None:
    app = FastAPI()
    app.add_middleware(
        SecurityHeadersMiddleware,
        runtime_profile="local",
        hsts_enabled=False,
        oidc_issuer="",
    )

    @app.get("/probe")
    def probe():
        return {"ok": True}

    response = TestClient(app).get("/probe")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in response.headers["Permissions-Policy"]
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert "Strict-Transport-Security" not in response.headers


def test_security_headers_hsts_only_on_production_https() -> None:
    app = FastAPI()
    app.add_middleware(
        SecurityHeadersMiddleware,
        runtime_profile="production",
        hsts_enabled=True,
        oidc_issuer="https://identity.example.test",
    )

    @app.get("/probe")
    def probe():
        return {"ok": True}

    client = TestClient(app, base_url="https://countyflow.example.test")
    response = client.get("/probe")

    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    csp = response.headers["Content-Security-Policy"]
    assert "unsafe-eval" not in csp
    assert "https://identity.example.test" in csp


def test_body_size_limit() -> None:
    app = FastAPI()
    app.add_middleware(
        JsonBodyLimitMiddleware,
        default_limit_bytes=64,
        route_limits={("POST", "/api/v1/ws-tickets"): 32},
    )

    @app.post("/api/v1/ws-tickets")
    async def echo(request: Request):
        return await request.json()

    response = TestClient(app).post(
        "/api/v1/ws-tickets",
        content=b'{"target_id":"' + (b"a" * 64) + b'"}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json() == {
        "code": "PAYLOAD_TOO_LARGE",
        "message": "The request payload is too large.",
    }


def test_body_size_limit_allows_bounded_json() -> None:
    app = FastAPI()
    app.add_middleware(JsonBodyLimitMiddleware, default_limit_bytes=64, route_limits={})

    @app.post("/echo")
    async def echo(request: Request):
        return await request.json()

    response = TestClient(app).post("/echo", json={"ok": True})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
