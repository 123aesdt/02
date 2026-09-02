from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

import jwt
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = PROJECT_ROOT / "loadtests" / "security_identity.py"


def _module():
    spec = importlib.util.spec_from_file_location("countyflow_loadtest_security_identity", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_loadtest_identity_is_unique_authenticated_and_secret_safe() -> None:
    module = _module()
    environment = {
        "RUNTIME_PROFILE": "docker-dev",
        "DEVELOPMENT_JWT_SECRET": "s" * 48,
        "AUTH_ISSUER": "countyflow-dev",
        "AUTH_AUDIENCE": "countyflow-api",
    }
    now = datetime.now(UTC)

    first = module.development_bearer_identity("SUPERVISOR", "worker-a", environment=environment, now=now)
    second = module.development_bearer_identity("SUPERVISOR", "worker-b", environment=environment, now=now)

    assert first.headers.keys() == {"Authorization"}
    assert first.headers["Authorization"].startswith("Bearer ")
    first_token = first.headers["Authorization"].removeprefix("Bearer ")
    second_token = second.headers["Authorization"].removeprefix("Bearer ")
    first_claims = jwt.decode(
        first_token,
        environment["DEVELOPMENT_JWT_SECRET"],
        algorithms=["HS256"],
        issuer=environment["AUTH_ISSUER"],
        audience=environment["AUTH_AUDIENCE"],
    )
    second_claims = jwt.decode(
        second_token,
        environment["DEVELOPMENT_JWT_SECRET"],
        algorithms=["HS256"],
        issuer=environment["AUTH_ISSUER"],
        audience=environment["AUTH_AUDIENCE"],
    )
    assert first_claims["roles"] == ["SUPERVISOR"]
    assert first_claims["sub"] != second_claims["sub"]
    assert first.metadata == {
        "authentication": "development_jwt",
        "authorization": "bearer",
        "role": "SUPERVISOR",
        "rate_limiting": "enabled",
        "principal_strategy": "unique_per_virtual_user",
    }
    assert first_token not in repr(first)
    assert environment["DEVELOPMENT_JWT_SECRET"] not in repr(first)
    assert "token" not in first.metadata


@pytest.mark.parametrize("profile", ["production", "staging"])
def test_loadtest_development_identity_fails_closed_outside_local_profiles(profile: str) -> None:
    module = _module()
    with pytest.raises(ValueError, match="local benchmark profiles"):
        module.development_bearer_identity(
            "DISPATCHER",
            "worker-a",
            environment={"RUNTIME_PROFILE": profile, "DEVELOPMENT_JWT_SECRET": "s" * 48},
        )


def test_loadtest_development_identity_rejects_missing_secret_and_unknown_role() -> None:
    module = _module()
    with pytest.raises(ValueError, match="not configured"):
        module.development_bearer_identity(
            "DISPATCHER", "worker-a", environment={"RUNTIME_PROFILE": "docker-dev"}
        )
    with pytest.raises(ValueError, match="role"):
        module.development_bearer_identity(
            "OWNER",
            "worker-a",
            environment={"RUNTIME_PROFILE": "docker-dev", "DEVELOPMENT_JWT_SECRET": "s" * 48},
        )


def test_existing_locust_workloads_use_per_user_bearer_and_no_actor_spoofing() -> None:
    standard = (PROJECT_ROOT / "loadtests" / "locustfile.py").read_text(encoding="utf-8")
    v2e = (PROJECT_ROOT / "loadtests" / "v2e_locustfile.py").read_text(encoding="utf-8")
    for source in (standard, v2e):
        assert "development_bearer_identity" in source
        assert "self.client.headers.update" in source
    assert '"operator_id"' not in v2e
