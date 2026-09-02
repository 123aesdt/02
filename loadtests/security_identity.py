"""Secret-safe, per-user identities for local authenticated load tests."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt

_LOCAL_PROFILES = frozenset({"local", "test", "docker-dev"})
_LOAD_ROLES = frozenset({"DISPATCHER", "SUPERVISOR"})


@dataclass(frozen=True)
class LoadtestIdentity:
    headers: dict[str, str] = field(repr=False)
    metadata: dict[str, str]


def development_bearer_identity(
    role: str,
    identity: str,
    *,
    environment: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> LoadtestIdentity:
    """Create one local-only JWT without exposing its token through repr/metadata."""
    values = os.environ if environment is None else environment
    profile = values.get("RUNTIME_PROFILE", "").strip().lower()
    if profile not in _LOCAL_PROFILES:
        raise ValueError("development load identities are restricted to local benchmark profiles")
    normalized_role = role.strip().upper()
    if normalized_role not in _LOAD_ROLES:
        raise ValueError("load-test role must be DISPATCHER or SUPERVISOR")
    secret = values.get("DEVELOPMENT_JWT_SECRET", "")
    if len(secret) < 32:
        raise ValueError("DEVELOPMENT_JWT_SECRET is not configured safely")
    normalized_identity = identity.strip()
    if not normalized_identity or len(normalized_identity) > 96:
        raise ValueError("load-test identity must be between 1 and 96 characters")

    issued_at = now or datetime.now(UTC)
    subject = f"loadtest-{normalized_role.lower()}-{normalized_identity}"
    token = jwt.encode(
        {
            "iss": values.get("AUTH_ISSUER", "countyflow-dev"),
            "aud": values.get("AUTH_AUDIENCE", "countyflow-api"),
            "sub": subject,
            "name": f"CountyFlow Load {normalized_role.title()}",
            "roles": [normalized_role],
            "iat": issued_at,
            "nbf": issued_at,
            "exp": issued_at + timedelta(minutes=15),
            "jti": uuid4().hex,
        },
        secret,
        algorithm="HS256",
    )
    return LoadtestIdentity(
        headers={"Authorization": f"Bearer {token}"},
        metadata={
            "authentication": "development_jwt",
            "authorization": "bearer",
            "role": normalized_role,
            "rate_limiting": "enabled",
            "principal_strategy": "unique_per_virtual_user",
        },
    )
