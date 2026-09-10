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
        build_runtime_graph(settings, object(), object())


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

    build_runtime_graph(settings, object(), object())
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


def test_docker_runtime_wires_mysql_sandtable_fleet_and_road_services(monkeypatch):
    captured: dict[str, object] = {}

    class RecordingSandtableRepository:
        def __init__(self, session):
            captured["sandtable_repository"] = session

    class RecordingFleetRepository:
        def __init__(self, session):
            captured["fleet_repository"] = session

    class RecordingCapacityProvider:
        def __init__(self, fleet_repository):
            captured["capacity_provider"] = (self, fleet_repository)

    class RecordingCapacityService:
        def __init__(self, provider, **kwargs):
            captured["capacity_service"] = (provider, kwargs)

    class RecordingRoadRepository:
        def __init__(self, session):
            captured.setdefault("road_repositories", []).append(self)

    class RecordingSnapshotService:
        def __init__(self, road_repository):
            captured["snapshot_repository"] = road_repository

    class RecordingFleetAllocationService:
        def __init__(self, fleet_repository, estimator):
            captured["fleet_allocation"] = (fleet_repository, estimator)

    class RecordingRoutingService:
        def __init__(self, route_provider, **kwargs):
            captured["routing"] = (route_provider, kwargs)

    monkeypatch.setattr(runtime_module, "SqlAlchemySandtableRepository", RecordingSandtableRepository)
    monkeypatch.setattr(runtime_module, "SqlAlchemyFleetRepository", RecordingFleetRepository)
    monkeypatch.setattr(runtime_module, "FleetCapacityProvider", RecordingCapacityProvider)
    monkeypatch.setattr(runtime_module, "CapacityService", RecordingCapacityService)
    monkeypatch.setattr(runtime_module, "SqlAlchemyRoadNetworkRepository", RecordingRoadRepository)
    monkeypatch.setattr(runtime_module, "RoadNetworkSnapshotService", RecordingSnapshotService)
    monkeypatch.setattr(runtime_module, "FleetAllocationService", RecordingFleetAllocationService)
    monkeypatch.setattr(runtime_module, "RoutingService", RecordingRoutingService)
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

    capacity_provider, capacity_repository = captured["capacity_provider"]
    capacity_service_provider, capacity_thresholds = captured["capacity_service"]
    fleet_allocation_repository, estimator = captured["fleet_allocation"]
    road_repositories = captured["road_repositories"]
    assert capacity_service_provider is capacity_provider
    assert capacity_repository is fleet_allocation_repository
    assert capacity_thresholds == {"limited_threshold": 0.8, "unavailable_threshold": 1.0}
    route_provider = captured["routing"][0]
    assert route_provider.resolve_route_reference("建议改走102国道") == "national-102"
    assert len(road_repositories) == 1
    assert captured["snapshot_repository"] is road_repositories[0]
    assert estimator._road_network is road_repositories[0]
    assert captured["routing"][1]["road_network_provider"] is road_repositories[0]
    assert "sandtable_repository" in captured
    assert "fleet_repository" in captured
    assert "fleet_allocation" in captured
