from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.security.dependencies import require_permission
from app.security.jwt_provider import DevelopmentJwtProvider
from app.security.models import AuthenticatedPrincipal, AuthMethod, Role
from app.security.permissions import ROLE_PERMISSION_MATRIX, Permission
from app.security.protocols import AuthenticationError, AuthenticationErrorCode


class PrincipalProvider:
    def __init__(self, principal: AuthenticatedPrincipal) -> None:
        self.principal = principal
        self.tokens: list[str] = []

    async def authenticate(self, token: str) -> AuthenticatedPrincipal:
        self.tokens.append(token)
        return self.principal


class Revocations:
    async def is_revoked(self, jti: str) -> bool:
        return False

    async def revoke(self, jti: str, expires_at: datetime) -> None:
        return None


RuntimeOverridePrincipal = Annotated[
    AuthenticatedPrincipal,
    Depends(require_permission(Permission.RUNTIME_OVERRIDE)),
]


def principal(role: Role = Role.DISPATCHER) -> AuthenticatedPrincipal:
    now = datetime.now(UTC)
    return AuthenticatedPrincipal(
        subject_id="subject-1",
        display_name="CountyFlow User",
        roles=frozenset({role}),
        permissions=ROLE_PERMISSION_MATRIX[role],
        auth_method=AuthMethod.DEVELOPMENT_JWT,
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
        jti="session-1",
    )


def test_principal_from_auth_provider() -> None:
    provider = PrincipalProvider(principal())
    app = create_app(authentication_provider=provider, revocation_store=Revocations())

    response = TestClient(app).get("/api/v1/auth/me", headers={"Authorization": "Bearer signed-token"})

    assert response.status_code == 200
    assert response.json()["subject_id"] == "subject-1"
    assert response.json()["roles"] == ["DISPATCHER"]
    assert "jti" not in response.json()
    assert provider.tokens == ["signed-token"]


def test_development_session_starts_without_manual_token(monkeypatch) -> None:
    monkeypatch.setenv("RUNTIME_PROFILE", "local")
    monkeypatch.setenv("AUTHENTICATION_PROVIDER", "development_jwt")
    monkeypatch.setenv("DEVELOPMENT_JWT_SECRET", "development-session-test-secret-value")
    monkeypatch.setenv("AUTH_ISSUER", "countyflow-dev")
    monkeypatch.setenv("AUTH_AUDIENCE", "countyflow-api")
    get_settings.cache_clear()
    try:
        app = create_app(revocation_store=Revocations())
        client = TestClient(app)

        session = client.post("/api/v1/auth/development-session")

        assert session.status_code == 200
        payload = session.json()
        assert payload["token_type"] == "bearer"
        assert payload["expires_in"] == 600
        assert payload["principal"]["roles"] == ["ADMIN"]
        authenticated = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {payload['access_token']}"},
        )
        assert authenticated.status_code == 200
        assert authenticated.json()["subject_id"] == "dev-admin"
    finally:
        get_settings.cache_clear()


def test_development_session_is_unavailable_outside_development_runtime(monkeypatch) -> None:
    monkeypatch.setenv("RUNTIME_PROFILE", "local")
    monkeypatch.setenv("AUTHENTICATION_PROVIDER", "development_jwt")
    monkeypatch.setenv("DEVELOPMENT_JWT_SECRET", "development-session-test-secret-value")
    get_settings.cache_clear()
    try:
        app = create_app(revocation_store=Revocations())
        app.state.runtime_profile = "production"

        response = TestClient(app).post("/api/v1/auth/development-session")

        assert response.status_code == 404
        assert "access_token" not in response.text
    finally:
        get_settings.cache_clear()


def test_missing_token_401() -> None:
    provider = PrincipalProvider(principal())
    response = TestClient(create_app(authentication_provider=provider, revocation_store=Revocations())).get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json() == {"code": "AUTHENTICATION_REQUIRED", "message": "Authentication is required."}
    assert response.headers["www-authenticate"] == "Bearer"
    assert provider.tokens == []


class DeniedProvider:
    def __init__(self, code: AuthenticationErrorCode) -> None:
        self.code = code

    async def authenticate(self, token: str) -> AuthenticatedPrincipal:
        raise AuthenticationError(self.code)


def test_invalid_token_401() -> None:
    app = create_app(authentication_provider=DeniedProvider(AuthenticationErrorCode.TOKEN_INVALID), revocation_store=Revocations())
    response = TestClient(app).get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid-secret-token"})

    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_INVALID"
    assert "invalid-secret-token" not in response.text


def test_expired_token_401() -> None:
    app = create_app(authentication_provider=DeniedProvider(AuthenticationErrorCode.TOKEN_EXPIRED), revocation_store=Revocations())
    response = TestClient(app).get("/api/v1/auth/me", headers={"Authorization": "Bearer expired-secret-token"})

    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_EXPIRED"
    assert "expired-secret-token" not in response.text


def test_wrong_audience_401() -> None:
    secret = "development-secret-value-32-chars"
    now = datetime.now(UTC)
    raw = jwt.encode(
        {
            "iss": "countyflow-dev",
            "aud": "wrong-api",
            "sub": "subject-1",
            "name": "User",
            "roles": ["DISPATCHER"],
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=5),
            "jti": "session-1",
        },
        secret,
        algorithm="HS256",
    )
    provider = DevelopmentJwtProvider(secret, issuer="countyflow-dev", audience="countyflow-api", revocations=Revocations())
    app = create_app(authentication_provider=provider, revocation_store=Revocations())

    response = TestClient(app).get("/api/v1/auth/me", headers={"Authorization": f"Bearer {raw}"})

    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_INVALID"
    assert raw not in response.text


def test_permission_denied_403() -> None:
    app = create_app(authentication_provider=PrincipalProvider(principal(Role.DISPATCHER)), revocation_store=Revocations())

    async def protected(_principal: RuntimeOverridePrincipal):
        return {"allowed": True}

    app.add_api_route("/test/runtime-override", protected, methods=["POST"])
    response = TestClient(app).post("/test/runtime-override", headers={"Authorization": "Bearer signed-token"})

    assert response.status_code == 403
    assert response.json() == {"code": "AUTHORIZATION_DENIED", "message": "Permission is required."}
