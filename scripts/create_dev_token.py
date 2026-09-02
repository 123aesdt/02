"""Create one short-lived CountyFlow development JWT for local user handoff."""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.security.permissions import Role


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Create a short-lived, role-limited CountyFlow development JWT.")
    value.add_argument("--role", required=True, choices=[role.value for role in Role])
    value.add_argument("--ttl-seconds", type=int, default=600)
    return value


def main() -> int:
    arguments = parser().parse_args()
    profile = os.getenv("RUNTIME_PROFILE", "local").strip().lower()
    if profile == "production":
        print("Development JWT creation is forbidden in production.", file=sys.stderr)
        return 2
    if profile not in {"local", "test", "docker-dev"}:
        print("RUNTIME_PROFILE must be local, test, or docker-dev.", file=sys.stderr)
        return 2
    if arguments.ttl_seconds < 1 or arguments.ttl_seconds > 900:
        print("Development JWT TTL must be between 1 and 900 seconds.", file=sys.stderr)
        return 2
    secret = os.getenv("DEVELOPMENT_JWT_SECRET", "")
    if len(secret) < 32:
        print("DEVELOPMENT_JWT_SECRET is not configured with at least 32 characters.", file=sys.stderr)
        return 2

    now = datetime.now(UTC)
    role = Role(arguments.role)
    subject = f"dev-{role.value.lower()}"
    token = jwt.encode(
        {
            "iss": os.getenv("AUTH_ISSUER", "countyflow-dev"),
            "aud": os.getenv("AUTH_AUDIENCE", "countyflow-api"),
            "sub": subject,
            "name": f"CountyFlow {role.value.title()}",
            "roles": [role.value],
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(seconds=arguments.ttl_seconds),
            "jti": uuid.uuid4().hex,
        },
        secret,
        algorithm="HS256",
    )
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
