from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_reports_backend_identity_and_safe_runtime_diagnostics(monkeypatch):
    settings = Settings(
        _env_file=None,
        runtime_profile="docker-dev",
        authentication_provider="development_jwt",
        development_jwt_secret="t" * 48,
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
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "countyflow-backend",
        "version": "0.1.0",
        "runtime": {
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
        },
    }
