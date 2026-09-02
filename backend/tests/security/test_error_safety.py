from datetime import datetime

from fastapi.testclient import TestClient

from app.main import create_app
from app.security.models import AuthenticatedPrincipal
from app.security.protocols import AuthenticationProviderUnavailable


class FailedProvider:
    async def authenticate(self, token: str) -> AuthenticatedPrincipal:
        raise AuthenticationProviderUnavailable from RuntimeError("Bearer secret-provider-token database-password")


class Revocations:
    async def is_revoked(self, jti: str) -> bool:
        return False

    async def revoke(self, jti: str, expires_at: datetime) -> None:
        return None


def test_error_response_no_secret() -> None:
    app = create_app(authentication_provider=FailedProvider(), revocation_store=Revocations())

    response = TestClient(app).get("/api/v1/auth/me", headers={"Authorization": "Bearer request-secret-token"})

    assert response.status_code == 503
    assert response.json() == {"code": "AUTHENTICATION_UNAVAILABLE", "message": "Authentication is temporarily unavailable."}
    assert "secret" not in response.text.lower()

