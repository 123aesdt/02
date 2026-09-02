import pytest
from fakeredis.aioredis import FakeRedis
from qdrant_client import QdrantClient

import app.runtime as runtime_module
from app.core.config import Settings
from app.events.broker import InMemoryTaskEventBroker
from app.graph_memory.service import GraphMemoryService
from app.providers.environment import HttpEnvironmentProvider
from app.runtime import (
    build_environment_provider,
    build_graph_memory_service,
    build_runtime_graph,
    build_shared_memory_service,
)
from app.shared_memory.service import SharedMemoryMutationService


def test_runtime_graph_rejects_production_until_real_provider_wiring_exists():
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
    )

    with pytest.raises(RuntimeError, match="Production runtime provider wiring is not implemented"):
        build_runtime_graph(settings, object())


def test_docker_http_environment_provider_uses_the_configured_timeout_boundary():
    settings = Settings(
        _env_file=None,
        runtime_profile="docker-dev",
        authentication_provider="development_jwt",
        development_jwt_secret="t" * 48,
        embedding_provider="fake",
        environment_provider="http",
        environment_api_base_url="http://host.docker.internal:18080",
        environment_api_timeout_seconds=0.8,
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

    provider = build_environment_provider(settings)

    assert isinstance(provider, HttpEnvironmentProvider)


def test_runtime_graph_memory_factory_respects_disabled_and_neo4j_backends():
    disabled = Settings(_env_file=None, graph_memory_backend="disabled")
    enabled = Settings(_env_file=None, graph_memory_backend="neo4j", neo4j_password="test-graph-secret")

    assert build_graph_memory_service(disabled, object()) is None
    assert isinstance(build_graph_memory_service(enabled, object()), GraphMemoryService)


def test_runtime_builds_shared_memory_service_through_narrow_boundaries():
    settings = Settings(_env_file=None, graph_memory_backend="neo4j", neo4j_password="test-graph-secret")

    service = build_shared_memory_service(
        settings,
        FakeRedis(decode_responses=False),
        QdrantClient(":memory:"),
        object(),
        InMemoryTaskEventBroker(),
    )

    assert isinstance(service, SharedMemoryMutationService)


def test_runtime_builders_use_the_configured_embedding_dimension(monkeypatch):
    captured: dict[str, int] = {}

    class RecordingRepository:
        def __init__(self, client, collection_name, vector_dimension):
            captured["entity_memory_repository"] = vector_dimension

    class RecordingProjection:
        def __init__(self, client, collection_name, vector_dimension):
            captured["shared_memory_projection"] = vector_dimension

    monkeypatch.setattr(runtime_module, "QdrantMemoryRepository", RecordingRepository)
    monkeypatch.setattr(runtime_module, "QdrantMemoryProjection", RecordingProjection)
    settings = Settings(_env_file=None, embedding_dimension=16)

    build_runtime_graph(settings, object())
    build_shared_memory_service(
        settings,
        FakeRedis(decode_responses=False),
        object(),
        object(),
        InMemoryTaskEventBroker(),
    )

    assert captured == {
        "entity_memory_repository": 16,
        "shared_memory_projection": 16,
    }


def test_docker_runtime_capacity_catalog_covers_seeded_demo_assignments(monkeypatch):
    captured: dict[tuple[str, str], object] = {}

    class RecordingCapacityProvider:
        def __init__(self, records):
            captured.update(records)

    monkeypatch.setattr(runtime_module, "InMemoryCapacityProvider", RecordingCapacityProvider)
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
        worker_retry_base_delay_ms=100,
        worker_idempotency_lock_ttl_ms=2_000,
    )

    build_runtime_graph(settings, object(), object())

    assert set(captured) == {
        ("demo-driver-li", "demo-vehicle-001"),
        ("demo-driver-zhang", "demo-vehicle-002"),
        ("demo-driver-chen", "demo-vehicle-003"),
        ("demo-driver-wang", "demo-vehicle-004"),
        ("demo-driver-lin", "demo-vehicle-005"),
        ("demo-driver-huang", "demo-vehicle-006"),
        ("demo-driver-zhou", "demo-vehicle-007"),
        ("demo-driver-xu", "demo-vehicle-008"),
        ("demo-driver-guo", "demo-vehicle-009"),
        ("demo-driver-yang", "demo-vehicle-010"),
    }
    first = captured[("demo-driver-li", "demo-vehicle-001")]
    assert first.driver_available is True
    assert first.vehicle_available is True
