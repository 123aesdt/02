from decimal import Decimal

from app.audit.service import AuditService
from app.capacity.provider import FleetCapacityProvider
from app.capacity.service import CapacityService
from app.core.config import Settings
from app.core.database import build_session_factory
from app.dispatch.service import DispatchService
from app.events.factory import create_task_event_broker
from app.fleet.service import DijkstraTravelTimeEstimator, FleetAllocationService
from app.fleet.sqlalchemy_repository import SqlAlchemyFleetRepository
from app.graph.builder import NODE_ORDER, build_graph
from app.graph.dependencies import GraphDependencies
from app.graph_memory.extractor import DeterministicGraphTripleExtractor
from app.graph_memory.neo4j_repository import Neo4jGraphMemoryRepository
from app.graph_memory.service import GraphMemoryService
from app.idempotency.service import IdempotencyService
from app.locks.redis_execution_lock import RedisExecutionLock
from app.memory.qdrant_repository import QdrantMemoryRepository
from app.memory.service import EntityMemoryService
from app.models.base import utc_now
from app.observability.recorder import MetricsRecorder
from app.observability.runtime import get_process_observability
from app.providers.embedding.fake import FakeEmbeddingProvider
from app.providers.environment import EnvironmentProvider, EnvironmentResult, HttpEnvironmentProvider, StaticRouteFallbackProvider
from app.publications.service import DispatchPublicationService
from app.road_network.dijkstra import DijkstraPathFinder
from app.road_network.service import RoadNetworkSnapshotService
from app.road_network.sqlalchemy_repository import SqlAlchemyRoadNetworkRepository
from app.routing.provider import InMemoryRouteProvider
from app.routing.service import RoutingService
from app.runtime_threads.checkpoint_store import RedisRuntimeCheckpointStore
from app.runtime_threads.events import RuntimeThreadEventPublisher
from app.runtime_threads.reconciler import ThreadCheckpointReconciler
from app.runtime_threads.runner import CheckpointedGraphRunner
from app.runtime_threads.sqlalchemy_repository import SqlAlchemyRuntimeThreadRepository
from app.sandtable.service import SandtableContextService
from app.sandtable.sqlalchemy_repository import SqlAlchemySandtableRepository
from app.services.circuit_breaker import CircuitBreaker
from app.services.environment import EnvironmentService
from app.shared_memory.events import MemoryMutationEventPublisher
from app.shared_memory.neo4j_projection import Neo4jMemoryProjection
from app.shared_memory.policy import MemoryPolicySettings
from app.shared_memory.projection_builder import DefaultMemoryProjectionBuilder
from app.shared_memory.qdrant_projection import QdrantMemoryProjection
from app.shared_memory.redis_lock import MemoryMutationLock
from app.shared_memory.service import SharedMemoryMutationService
from app.shared_memory.sqlalchemy_repository import SqlAlchemyMemoryControlRepository
from app.streams.redis_queue import RedisStreamQueue
from app.vehicle_operations.dispatch_bridge import SqlAlchemyVehicleBreakdownHandler
from app.vehicle_operations.query_service import SystemClock
from app.vehicle_operations.service import RescueOrchestrationService
from app.vehicle_operations.sqlalchemy_repository import SqlAlchemyVehicleOperationsRepository
from app.workers.dispatch_worker import DispatchWorker


class DockerDevelopmentEnvironmentProvider:
    """Deterministic local Docker environment input; no external API is required."""

    async def get_environment(self, route_id: str) -> EnvironmentResult:
        return EnvironmentResult("heavy_rain", "slippery", "high", "docker_development", False, None, 0.0)


def build_environment_provider(settings: Settings) -> EnvironmentProvider:
    if settings.environment_provider == "http":
        return HttpEnvironmentProvider(
            settings.environment_api_base_url,
            timeout_seconds=settings.environment_api_timeout_seconds,
        )
    return DockerDevelopmentEnvironmentProvider()


def build_graph_memory_service(settings: Settings, neo4j_driver: object | None) -> GraphMemoryService | None:
    if settings.graph_memory_backend == "disabled":
        return None
    if settings.graph_memory_backend == "fake":
        raise RuntimeError("Fake graph memory is test-only and must be injected explicitly.")
    if neo4j_driver is None:
        raise RuntimeError("A Neo4j driver is required for the configured graph memory backend.")
    return GraphMemoryService(
        Neo4jGraphMemoryRepository(
            neo4j_driver,
            settings.neo4j_database,
            query_timeout_seconds=settings.neo4j_query_timeout_seconds,
        ),
        DeterministicGraphTripleExtractor(),
        max_hops=settings.graph_memory_max_hops,
        result_limit=settings.graph_memory_result_limit,
    )


def build_runtime_graph(
    settings: Settings,
    qdrant_client: object,
    neo4j_driver: object | None = None,
    *,
    checkpointer: object | None = None,
    metrics: MetricsRecorder | None = None,
):
    if settings.runtime_profile == "production":
        raise RuntimeError("Production runtime provider wiring is not implemented; use an explicitly verified real-provider runtime before production.")
    session_factory = build_session_factory(settings.database_url)
    actual_metrics = metrics or get_process_observability(settings.metrics_enabled, settings.metrics_host, settings.metrics_port).recorder
    embedding = FakeEmbeddingProvider(dimension=settings.embedding_dimension)
    memory = EntityMemoryService(
        embedding,
        QdrantMemoryRepository(qdrant_client, "entity_resolution_memory", embedding.vector_dimension),
    )
    fleet_repository = SqlAlchemyFleetRepository(session_factory)
    road_network_repository = SqlAlchemyRoadNetworkRepository(session_factory)
    dependencies = GraphDependencies(
        entity_memory_service=memory,
        graph_memory_service=build_graph_memory_service(settings, neo4j_driver),
        environment_service=EnvironmentService(
            build_environment_provider(settings),
            StaticRouteFallbackProvider(),
            CircuitBreaker(settings.environment_cb_failure_threshold, settings.environment_cb_recovery_seconds),
        ),
        capacity_service=CapacityService(
            FleetCapacityProvider(fleet_repository),
            limited_threshold=settings.capacity_limited_threshold,
            unavailable_threshold=settings.capacity_unavailable_threshold,
        ),
        sandtable_context_service=SandtableContextService(SqlAlchemySandtableRepository(session_factory)),
        road_network_snapshot_service=RoadNetworkSnapshotService(road_network_repository),
        fleet_allocation_service=FleetAllocationService(
            fleet_repository,
            DijkstraTravelTimeEstimator(road_network_repository, DijkstraPathFinder()),
        ),
        routing_service=RoutingService(
            InMemoryRouteProvider.default_catalog(),
            memory_adoption_threshold=settings.memory_adoption_threshold,
            road_network_provider=road_network_repository,
            path_finder=DijkstraPathFinder(),
        ),
        dispatch_service=DispatchService(session_factory),
        audit_service=AuditService(session_factory),
        metrics=actual_metrics,
    )
    interrupt_after = [settings.runtime_checkpoint_interrupt_after] if settings.runtime_checkpoint_interrupt_after else None
    return build_graph(
        dependencies,
        checkpointer=checkpointer,
        interrupt_after=interrupt_after,
    )


def build_shared_memory_service(
    settings: Settings,
    redis_client: object,
    qdrant_client: object,
    neo4j_driver: object,
    event_broker: object,
    metrics: MetricsRecorder | None = None,
) -> SharedMemoryMutationService:
    embedding = FakeEmbeddingProvider(dimension=settings.embedding_dimension)
    return SharedMemoryMutationService(
        repository=SqlAlchemyMemoryControlRepository(build_session_factory(settings.database_url)),
        lock=MemoryMutationLock(
            redis_client,
            ttl_ms=settings.memory_mutation_lock_ttl_ms,
        ),
        policy_settings=MemoryPolicySettings(
            Decimal(str(settings.memory_auto_apply_min_confidence)),
            Decimal(str(settings.memory_lower_confidence_reject_delta)),
        ),
        vector_projection=QdrantMemoryProjection(
            qdrant_client,
            "entity_resolution_memory",
            embedding.vector_dimension,
        ),
        graph_projection=Neo4jMemoryProjection(
            neo4j_driver,
            settings.neo4j_database,
            query_timeout_seconds=settings.neo4j_query_timeout_seconds,
        ),
        projection_builder=DefaultMemoryProjectionBuilder(embedding),
        event_publisher=MemoryMutationEventPublisher(event_broker),
        clock=utc_now,
        timeout_seconds=settings.memory_mutation_timeout_seconds,
        metrics=metrics,
    )


def build_runtime_worker(settings: Settings, redis_client: object, qdrant_client: object, neo4j_driver: object | None = None) -> DispatchWorker:
    metrics = get_process_observability(settings.metrics_enabled, settings.metrics_host, settings.metrics_port).recorder
    session_factory = build_session_factory(settings.database_url)
    event_broker = create_task_event_broker(settings, redis_client)
    checkpoint_store = RedisRuntimeCheckpointStore.from_redis_client(
        redis_client,
        ttl_minutes=settings.runtime_checkpoint_retention_minutes,
        refresh_on_read=settings.runtime_checkpoint_refresh_on_read,
        namespace=settings.runtime_checkpoint_namespace,
        metrics=metrics,
    )
    runtime_thread_repository = SqlAlchemyRuntimeThreadRepository(session_factory)
    graph = build_runtime_graph(
        settings,
        qdrant_client,
        neo4j_driver,
        checkpointer=checkpoint_store.native_checkpointer,
        metrics=metrics,
    )
    runtime_runner = CheckpointedGraphRunner(
        graph,
        runtime_thread_repository,
        checkpoint_store,
        node_order=NODE_ORDER,
        max_checkpoint_bytes=settings.runtime_checkpoint_max_bytes,
        worker_consumer=settings.worker_consumer_name,
        event_publisher=RuntimeThreadEventPublisher(
            event_broker,
            runtime_thread_repository,
        ),
        metrics=metrics,
    )
    runtime_reconciler = ThreadCheckpointReconciler(
        runtime_thread_repository,
        checkpoint_store,
        node_order=NODE_ORDER,
        scan_limit=settings.runtime_checkpoint_reconciliation_scan_limit,
        max_checkpoint_bytes=settings.runtime_checkpoint_max_bytes,
        worker_consumer=settings.worker_consumer_name,
    )
    queue = RedisStreamQueue(
        redis_client,
        settings.redis_stream_name,
        settings.redis_consumer_group,
        settings.worker_consumer_name,
        dlq_stream_name=settings.redis_dlq_stream_name,
    )
    vehicle_repository = SqlAlchemyVehicleOperationsRepository(session_factory)
    vehicle_breakdown_handler = SqlAlchemyVehicleBreakdownHandler(
        session_factory,
        RescueOrchestrationService(
            vehicle_repository,
            SqlAlchemyRoadNetworkRepository(session_factory),
            DijkstraPathFinder(),
            SystemClock(),
        ),
    )
    return DispatchWorker(
        queue,
        graph,
        read_count=settings.worker_read_count,
        block_ms=settings.worker_block_ms,
        consumer_name=settings.worker_consumer_name,
        pending_min_idle_ms=settings.worker_pending_min_idle_ms,
        recovery_count=settings.worker_recovery_count,
        idempotency_service=IdempotencyService(session_factory),
        execution_lock=RedisExecutionLock(redis_client, ttl_ms=settings.worker_idempotency_lock_ttl_ms),
        event_broker=event_broker,
        runtime_runner=runtime_runner,
        runtime_thread_repository=runtime_thread_repository,
        runtime_thread_reconciler=runtime_reconciler,
        automatic_publication_service=DispatchPublicationService(session_factory),
        vehicle_breakdown_handler=vehicle_breakdown_handler,
        metrics=metrics,
    )
