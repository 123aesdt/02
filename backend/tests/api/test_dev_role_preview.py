from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.security.permissions import ROLE_PERMISSION_MATRIX, Role


class Revocations:
    async def is_revoked(self, jti: str) -> bool:
        return False

    async def revoke(self, jti: str, expires_at: datetime) -> None:
        return None


@pytest.fixture
def development_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("RUNTIME_PROFILE", "local")
    monkeypatch.setenv("AUTHENTICATION_PROVIDER", "development_jwt")
    monkeypatch.setenv("DEVELOPMENT_JWT_SECRET", "development-session-test-secret-value")
    monkeypatch.setenv("AUTH_ISSUER", "countyflow-dev")
    monkeypatch.setenv("AUTH_AUDIENCE", "countyflow-api")
    get_settings.cache_clear()
    client = TestClient(create_app(revocation_store=Revocations()))
    yield client
    get_settings.cache_clear()


@pytest.mark.parametrize("role", list(Role))
def test_dev_role_identity_server_issued(development_client: TestClient, role: Role) -> None:
    session = development_client.post("/api/v1/auth/development-session", json={"role": role.value})

    assert session.status_code == 200
    payload = session.json()
    assert payload["principal"]["subject_id"] == f"dev-{role.value.lower()}"
    assert payload["principal"]["roles"] == [role.value]
    assert set(payload["principal"]["permissions"]) == {permission.value for permission in ROLE_PERMISSION_MATRIX[role]}

    authenticated = development_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert authenticated.status_code == 200
    assert authenticated.json()["roles"] == [role.value]


def test_client_cannot_self_escalate_dev_role(development_client: TestClient) -> None:
    response = development_client.post(
        "/api/v1/auth/development-session",
        json={"role": "DISPATCHER", "permissions": ["system:admin"]},
    )

    assert response.status_code == 422
    assert "access_token" not in response.text


def test_production_dev_role_endpoint_rejected(monkeypatch) -> None:
    monkeypatch.setenv("RUNTIME_PROFILE", "local")
    monkeypatch.setenv("AUTHENTICATION_PROVIDER", "development_jwt")
    monkeypatch.setenv("DEVELOPMENT_JWT_SECRET", "development-session-test-secret-value")
    get_settings.cache_clear()
    try:
        app = create_app(revocation_store=Revocations())
        app.state.runtime_profile = "production"
        response = TestClient(app).post(
            "/api/v1/auth/development-session",
            json={"role": "ADMIN"},
        )

        assert response.status_code == 404
        assert "access_token" not in response.text
    finally:
        get_settings.cache_clear()


def test_unknown_dev_role_is_rejected(development_client: TestClient) -> None:
    response = development_client.post(
        "/api/v1/auth/development-session",
        json={"role": "ROOT"},
    )

    assert response.status_code == 422
    assert "access_token" not in response.text
