from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from app.security.models import AuthenticatedPrincipal, AuthMethod, Role
from app.security.permissions import Permission


def test_principal_from_auth_provider() -> None:
    issued_at = datetime(2026, 8, 28, 8, tzinfo=UTC)
    principal = AuthenticatedPrincipal(
        subject_id="operator-17",
        display_name="Li Supervisor",
        roles=frozenset({Role.SUPERVISOR}),
        permissions=frozenset({Permission.RUNTIME_READ, Permission.RUNTIME_OVERRIDE}),
        auth_method=AuthMethod.OIDC_JWT,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(minutes=10),
        jti="session-17",
    )

    assert principal.subject_id == "operator-17"
    assert principal.can(Permission.RUNTIME_OVERRIDE) is True
    assert principal.can(Permission.SYSTEM_ADMIN) is False
    assert principal.to_public_dict() == {
        "subject_id": "operator-17",
        "display_name": "Li Supervisor",
        "roles": ["SUPERVISOR"],
        "permissions": ["runtime:override", "runtime:read"],
        "auth_method": "oidc_jwt",
        "issued_at": "2026-08-28T08:00:00+00:00",
        "expires_at": "2026-08-28T08:10:00+00:00",
    }
    assert "session-17" not in repr(principal.to_public_dict())
    with pytest.raises(FrozenInstanceError):
        principal.subject_id = "spoofed"  # type: ignore[misc]


@pytest.mark.parametrize("field", ["subject_id", "display_name", "jti"])
def test_principal_rejects_empty_identity_fields(field: str) -> None:
    issued_at = datetime.now(UTC)
    values = {
        "subject_id": "subject",
        "display_name": "Display",
        "roles": frozenset({Role.DISPATCHER}),
        "permissions": frozenset({Permission.DISPATCH_READ}),
        "auth_method": AuthMethod.DEVELOPMENT_JWT,
        "issued_at": issued_at,
        "expires_at": issued_at + timedelta(minutes=5),
        "jti": "jti",
    }
    values[field] = " "

    with pytest.raises(ValueError, match=field):
        AuthenticatedPrincipal(**values)


def test_principal_rejects_non_utc_or_non_future_expiry() -> None:
    issued_at = datetime(2026, 8, 28, 8, tzinfo=UTC)
    with pytest.raises(ValueError, match="expires_at"):
        AuthenticatedPrincipal(
            subject_id="subject",
            display_name="Display",
            roles=frozenset({Role.DISPATCHER}),
            permissions=frozenset({Permission.DISPATCH_READ}),
            auth_method=AuthMethod.DEVELOPMENT_JWT,
            issued_at=issued_at,
            expires_at=issued_at,
            jti="jti",
        )
