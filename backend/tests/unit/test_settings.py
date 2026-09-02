import json

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_rejects_metrics_with_multiple_processes_without_multiprocess_dir():
    with pytest.raises(ValueError, match="PROMETHEUS_MULTIPROC_DIR"):
        Settings(
            _env_file=None,
            runtime_profile="production",
            authentication_provider="oidc_jwt",
            auth_issuer="https://identity.example.test/",
            auth_audience="countyflow-api",
            auth_jwks_url="https://identity.example.test/.well-known/jwks.json",
            cors_allowed_origins="https://countyflow.example.test",
            embedding_provider="openai_compatible",
            environment_provider="http",
            environment_api_base_url="https://environment.example.test",
            capacity_provider="real",
            routing_provider="real",
            database_backend="mysql",
            redis_backend="server",
            qdrant_backend="server",
            graph_memory_backend="neo4j",
            neo4j_password="safe-test-value",
            metrics_enabled=True,
            backend_processes=2,
        )


def test_settings_loads_environment_without_exposing_secrets(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("LLM_API_KEY", "secret-llm")
    monkeypatch.setenv("EMBEDDING_API_KEY", "secret-embedding")

    settings = Settings()

    assert settings.app_name == "CountyFlow AI"
    assert settings.app_env == "test"
    assert str(settings.database_url) == "sqlite+pysqlite:///:memory:"
    assert "secret-llm" not in repr(settings)
    assert "secret-embedding" not in repr(settings)


def test_settings_expose_redis_stream_configuration():
    settings = Settings()

    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.redis_stream_name == "countyflow:dispatch:tasks"
    assert settings.redis_consumer_group == "countyflow-workers"
    assert settings.redis_consumer_name == "worker-1"


def test_embedding_dimension_is_positive_and_configurable():
    assert Settings(_env_file=None, embedding_dimension=16).embedding_dimension == 16

    with pytest.raises(ValidationError, match="embedding_dimension"):
        Settings(_env_file=None, embedding_dimension=0)


def test_settings_expose_worker_read_configuration():
    settings = Settings()

    assert settings.worker_consumer_name == "worker-1"
    assert settings.worker_read_count == 1
    assert settings.worker_block_ms == 1000


def test_settings_expose_idempotency_lock_ttl():
    settings = Settings()

    assert settings.worker_idempotency_lock_ttl_ms == 30000


def test_settings_expose_task_event_stream_configuration():
    settings = Settings()

    assert settings.task_event_broker == "memory"
    assert settings.task_event_stream_prefix == "countyflow:events:task"
    assert settings.task_event_history_maxlen == 100


def test_settings_expose_bounded_runtime_checkpoint_configuration():
    settings = Settings(_env_file=None)

    assert settings.runtime_checkpoint_backend == "redis"
    assert settings.runtime_checkpoint_namespace == "countyflow"
    assert settings.runtime_checkpoint_retention_minutes == 10_080
    assert settings.runtime_checkpoint_refresh_on_read is False
    assert settings.runtime_checkpoint_max_bytes == 1_048_576
    assert settings.runtime_checkpoint_reconciliation_scan_limit == 10


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("runtime_checkpoint_retention_minutes", 0, "retention"),
        ("runtime_checkpoint_max_bytes", 0, "max bytes"),
        ("runtime_checkpoint_reconciliation_scan_limit", 0, "scan limit"),
    ],
)
def test_settings_reject_invalid_runtime_checkpoint_bounds(field, value, message):
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, **{field: value})


def test_docker_dev_allows_declared_deterministic_providers():
    settings = Settings(
        _env_file=None,
        runtime_profile="docker-dev",
        authentication_provider="development_jwt",
        development_jwt_secret="x" * 32,
        embedding_provider="fake",
        environment_provider="docker-development",
        capacity_provider="in-memory",
        routing_provider="in-memory",
        database_backend="mysql",
        redis_backend="server",
        qdrant_backend="server",
        graph_memory_backend="neo4j",
        neo4j_password="test-graph-secret",
        worker_block_ms=250,
        worker_pending_min_idle_ms=2_500,
        worker_retry_base_delay_ms=250,
        worker_idempotency_lock_ttl_ms=2_000,
    )

    assert settings.runtime_profile == "docker-dev"
    assert settings.embedding_provider == "fake"


def test_docker_dev_rejects_pending_recovery_before_execution_lock_expiry():
    with pytest.raises(ValidationError, match="worker_pending_min_idle_ms must exceed worker_idempotency_lock_ttl_ms"):
        Settings(
            _env_file=None,
            runtime_profile="docker-dev",
            embedding_provider="fake",
            environment_provider="docker-development",
            capacity_provider="in-memory",
            routing_provider="in-memory",
            database_backend="mysql",
            redis_backend="server",
            qdrant_backend="server",
            graph_memory_backend="neo4j",
            neo4j_password="test-graph-secret",
            worker_pending_min_idle_ms=5_000,
            worker_idempotency_lock_ttl_ms=30_000,
        )


def test_docker_dev_rejects_a_configured_recovery_budget_at_or_above_five_seconds():
    with pytest.raises(ValidationError, match="configured worker recovery budget must be below 5000ms"):
        Settings(
            _env_file=None,
            runtime_profile="docker-dev",
            embedding_provider="fake",
            environment_provider="docker-development",
            capacity_provider="in-memory",
            routing_provider="in-memory",
            database_backend="mysql",
            redis_backend="server",
            qdrant_backend="server",
            graph_memory_backend="neo4j",
            neo4j_password="test-graph-secret",
            worker_block_ms=1_000,
            worker_pending_min_idle_ms=3_100,
            worker_retry_base_delay_ms=500,
            worker_idempotency_lock_ttl_ms=3_000,
        )


def test_docker_dev_allows_controlled_http_environment_acceptance():
    settings = Settings(
        _env_file=None,
        runtime_profile="docker-dev",
        authentication_provider="development_jwt",
        development_jwt_secret="x" * 32,
        embedding_provider="fake",
        environment_provider="http",
        environment_api_base_url="http://host.docker.internal:18080",
        capacity_provider="in-memory",
        routing_provider="in-memory",
        database_backend="mysql",
        redis_backend="server",
        qdrant_backend="server",
        graph_memory_backend="neo4j",
        neo4j_password="test-graph-secret",
        worker_block_ms=250,
        worker_pending_min_idle_ms=2_500,
        worker_retry_base_delay_ms=100,
        worker_idempotency_lock_ttl_ms=2_000,
    )

    assert settings.environment_provider == "http"


def test_worker_recovery_budget_includes_idle_scan_and_first_redelivery_backoff():
    settings = Settings(
        _env_file=None,
        runtime_profile="docker-dev",
        authentication_provider="development_jwt",
        development_jwt_secret="x" * 32,
        embedding_provider="fake",
        environment_provider="docker-development",
        capacity_provider="in-memory",
        routing_provider="in-memory",
        database_backend="mysql",
        redis_backend="server",
        qdrant_backend="server",
        graph_memory_backend="neo4j",
        neo4j_password="test-graph-secret",
        worker_block_ms=250,
        worker_pending_min_idle_ms=2_500,
        worker_retry_base_delay_ms=250,
        worker_idempotency_lock_ttl_ms=2_000,
    )

    assert settings.worker_recovery_budget_ms == 3_250


def test_production_rejects_fake_embedding():
    with pytest.raises(ValidationError, match="embedding_provider=fake"):
        Settings(
            _env_file=None,
            runtime_profile="production",
            embedding_provider="fake",
            environment_provider="http",
            capacity_provider="real",
            routing_provider="real",
            database_backend="mysql",
            redis_backend="server",
            qdrant_backend="server",
            graph_memory_backend="neo4j",
            neo4j_password="test-graph-secret",
        )


def test_production_rejects_development_environment_provider():
    with pytest.raises(ValidationError, match="environment_provider=docker-development"):
        Settings(
            _env_file=None,
            runtime_profile="production",
            embedding_provider="openai_compatible",
            environment_provider="docker-development",
            capacity_provider="real",
            routing_provider="real",
            database_backend="mysql",
            redis_backend="server",
            qdrant_backend="server",
            graph_memory_backend="neo4j",
            neo4j_password="test-graph-secret",
        )


def test_runtime_summary_exposes_labels_without_connections_or_secrets():
    settings = Settings(
        _env_file=None,
        runtime_profile="docker-dev",
        authentication_provider="development_jwt",
        development_jwt_secret="x" * 32,
        database_url="mysql+pymysql://user:database-secret@mysql/countyflow",
        redis_url="redis://:redis-secret@redis:6379/0",
        qdrant_url="http://qdrant:6333",
        embedding_provider="fake",
        embedding_api_key="embedding-secret",
        environment_provider="docker-development",
        capacity_provider="in-memory",
        routing_provider="in-memory",
        database_backend="mysql",
        redis_backend="server",
        qdrant_backend="server",
        graph_memory_backend="neo4j",
        neo4j_password="neo4j-secret",
        worker_block_ms=250,
        worker_pending_min_idle_ms=2_500,
        worker_retry_base_delay_ms=250,
        worker_idempotency_lock_ttl_ms=2_000,
    )

    summary = settings.runtime_summary()
    serialized = json.dumps(summary)

    assert summary == {
        "runtime_profile": "docker-dev",
        "embedding_provider": "fake",
        "environment_provider": "docker-development",
        "capacity_provider": "in-memory",
        "routing_provider": "in-memory",
        "database": "mysql",
        "redis": "server",
        "qdrant": "server",
        "graph_memory": "neo4j",
        "metrics": "disabled",
        "observability_api": "disabled",
    }
    assert "database-secret" not in serialized
    assert "redis-secret" not in serialized
    assert "embedding-secret" not in serialized
    assert "DATABASE_URL" not in serialized


def test_runtime_configuration_errors_hide_secret_inputs():
    with pytest.raises(ValidationError) as captured:
        Settings(
            _env_file=None,
            runtime_profile="production",
            authentication_provider="oidc_jwt",
            auth_issuer="https://identity.example.test/",
            auth_audience="countyflow-api",
            auth_jwks_url="https://identity.example.test/.well-known/jwks.json",
            cors_allowed_origins="https://countyflow.example.test",
            embedding_provider="fake",
            embedding_api_key="embedding-secret",
            database_url="mysql+pymysql://user:database-secret@mysql/countyflow",
            redis_url="redis://:redis-secret@redis:6379/0",
        )

    error_text = str(captured.value)
    assert "embedding-secret" not in error_text
    assert "database-secret" not in error_text
    assert "redis-secret" not in error_text


def test_local_graph_memory_is_disabled_by_default():
    settings = Settings(_env_file=None)

    assert settings.graph_memory_backend == "disabled"
    assert settings.runtime_summary()["graph_memory"] == "disabled"


def test_docker_dev_requires_real_neo4j_graph_store():
    with pytest.raises(ValidationError, match="graph_memory_backend=disabled"):
        Settings(
            _env_file=None,
            runtime_profile="docker-dev",
            embedding_provider="fake",
            environment_provider="docker-development",
            capacity_provider="in-memory",
            routing_provider="in-memory",
            database_backend="mysql",
            redis_backend="server",
            qdrant_backend="server",
            graph_memory_backend="disabled",
            worker_block_ms=250,
            worker_pending_min_idle_ms=2_500,
            worker_retry_base_delay_ms=100,
            worker_idempotency_lock_ttl_ms=2_000,
        )


def test_neo4j_password_is_secret_and_never_in_runtime_summary():
    settings = Settings(_env_file=None, neo4j_password="neo4j-super-secret")

    assert "neo4j-super-secret" not in repr(settings)
    assert "neo4j-super-secret" not in json.dumps(settings.runtime_summary())


def test_real_graph_store_requires_non_empty_connection_settings():
    with pytest.raises(ValidationError, match="Neo4j connection settings are required"):
        Settings(_env_file=None, graph_memory_backend="neo4j", neo4j_password="")


def test_production_protected_apis_use_the_unified_oidc_principal() -> None:
    settings = Settings(
        _env_file=None,
        runtime_profile="production",
        authentication_provider="oidc_jwt",
        auth_issuer="https://identity.example.test/",
        auth_audience="countyflow-api",
        auth_jwks_url="https://identity.example.test/.well-known/jwks.json",
        cors_allowed_origins="https://countyflow.example.test",
        embedding_provider="openai_compatible",
        environment_provider="http",
        capacity_provider="real",
        routing_provider="real",
        database_backend="mysql",
        redis_backend="server",
        qdrant_backend="server",
        graph_memory_backend="neo4j",
        neo4j_password="test-graph-secret",
        memory_mutation_api_enabled=True,
        runtime_thread_api_enabled=True,
        observability_api_enabled=True,
    )

    assert settings.authentication_provider == "oidc_jwt"
    assert not hasattr(settings, "memory_mutation_authorization_provider")
    assert not hasattr(settings, "runtime_thread_authorization_provider")
    assert not hasattr(settings, "observability_authorization_provider")


def test_production_rejects_checkpoint_crash_injection():
    with pytest.raises(ValidationError, match="checkpoint interrupt"):
        Settings(
            _env_file=None,
            runtime_profile="production",
            embedding_provider="openai_compatible",
            environment_provider="http",
            capacity_provider="real",
            routing_provider="real",
            database_backend="mysql",
            redis_backend="server",
            qdrant_backend="server",
            graph_memory_backend="neo4j",
            neo4j_password="test-graph-secret",
            runtime_checkpoint_interrupt_after="intake",
        )


def test_runtime_override_api_requires_environment_boundary():
    with pytest.raises(ValidationError, match="environment checkpoint boundary"):
        Settings(
            _env_file=None,
            runtime_override_api_enabled=True,
            runtime_checkpoint_interrupt_after="capacity",
        )


def test_runtime_override_lock_ttl_has_safety_margin():
    with pytest.raises(ValidationError, match="safety margin"):
        Settings(
            _env_file=None,
            runtime_override_timeout_seconds=4,
            runtime_override_lock_ttl_ms=5_999,
        )
