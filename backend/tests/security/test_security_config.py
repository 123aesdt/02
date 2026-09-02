import pytest
from pydantic import ValidationError

from app.core.config import Settings


def production_settings(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "_env_file": None,
        "runtime_profile": "production",
        "authentication_provider": "oidc_jwt",
        "auth_issuer": "https://identity.example.test/",
        "auth_audience": "countyflow-api",
        "auth_jwks_url": "https://identity.example.test/.well-known/jwks.json",
        "auth_algorithms": "RS256,ES256",
        "embedding_provider": "openai_compatible",
        "environment_provider": "http",
        "environment_api_base_url": "https://environment.example.test",
        "capacity_provider": "real",
        "routing_provider": "real",
        "database_backend": "mysql",
        "redis_backend": "server",
        "qdrant_backend": "server",
        "graph_memory_backend": "neo4j",
        "neo4j_password": "safe-test-value",
        "cors_allowed_origins": "https://countyflow.example.test",
    }
    values.update(overrides)
    return values


def test_production_dev_auth_rejected() -> None:
    with pytest.raises(ValidationError, match="development authentication"):
        Settings(**production_settings(authentication_provider="development_jwt", development_jwt_secret="x" * 32))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"authentication_provider": "disabled"}, "production authentication provider"),
        ({"auth_issuer": ""}, "issuer"),
        ({"auth_audience": ""}, "audience"),
        ({"auth_jwks_url": ""}, "JWKS"),
        ({"auth_algorithms": "HS256"}, "asymmetric"),
        ({"cors_allowed_origins": "*"}, "wildcard CORS"),
        ({"cors_allowed_origins": "http://countyflow.example.test"}, "HTTPS CORS"),
    ],
)
def test_production_security_configuration_fails_closed(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(**production_settings(**overrides))


def test_docker_dev_requires_signed_development_auth() -> None:
    common = {
        "_env_file": None,
        "runtime_profile": "docker-dev",
        "embedding_provider": "fake",
        "environment_provider": "docker-development",
        "capacity_provider": "in-memory",
        "routing_provider": "in-memory",
        "database_backend": "mysql",
        "redis_backend": "server",
        "qdrant_backend": "server",
        "graph_memory_backend": "neo4j",
        "neo4j_password": "test-graph-secret",
        "worker_block_ms": 250,
        "worker_pending_min_idle_ms": 2_500,
        "worker_retry_base_delay_ms": 250,
        "worker_idempotency_lock_ttl_ms": 2_000,
    }
    with pytest.raises(ValidationError, match="development_jwt"):
        Settings(**common, authentication_provider="disabled")
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(**common, authentication_provider="development_jwt", development_jwt_secret="too-short")

    settings = Settings(**common, authentication_provider="development_jwt", development_jwt_secret="x" * 32)
    assert settings.authentication_provider == "development_jwt"
    assert "x" * 32 not in repr(settings)


def test_rate_limit_policy_is_configurable_and_positive() -> None:
    settings = Settings(_env_file=None)

    assert settings.rate_limit_dispatch_submit_capacity == 30
    assert settings.rate_limit_dispatch_submit_refill_per_minute == 120
    assert settings.rate_limit_runtime_override_capacity == 3
    assert settings.rate_limit_memory_mutation_capacity == 5
    assert settings.rate_limit_observability_read_capacity == 60
    assert settings.rate_limit_ws_ticket_capacity == 10

    with pytest.raises(ValidationError, match="rate-limit"):
        Settings(_env_file=None, rate_limit_runtime_override_capacity=0)
