import asyncio

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from qdrant_client import QdrantClient
from redis.asyncio import Redis
from sqlalchemy import inspect

from app.anomaly_reports.service import AnomalyReportService
from app.anomaly_reports.sqlalchemy_repository import SqlAlchemyAnomalyReportRepository
from app.api.v1.anomaly_reports import router as anomaly_reports_router
from app.api.v1.auth import router as auth_router
from app.api.v1.demo_scenarios import router as demo_scenarios_router
from app.api.v1.dispatch_tasks import router as dispatch_tasks_router
from app.api.v1.memory_mutations import router as memory_mutations_router
from app.api.v1.observability import router as observability_router
from app.api.v1.review_decisions import router as review_decisions_router
from app.api.v1.runtime_overrides import router as runtime_overrides_router
from app.api.v1.runtime_threads import router as runtime_threads_router
from app.api.v1.security_audit import router as security_audit_router
from app.api.v1.task_events import router as task_events_router
from app.api.v1.vehicle_operations import router as vehicle_operations_router
from app.api.v1.workspace_reads import router as workspace_reads_router
from app.api.v1.ws_tickets import router as ws_tickets_router
from app.core.config import get_settings
from app.core.database import build_session_factory
from app.core.errors import OptimisticLockConflict
from app.demo_reset import DemoScenarioResetService
from app.events.factory import create_task_event_broker
from app.graph_memory.driver import build_neo4j_driver
from app.observability.bootstrap import build_backend_observability_runtime
from app.observability.correlation import CorrelationMiddleware
from app.observability.http import MetricsMiddleware
from app.observability.logging import configure_structured_logging
from app.observability.prometheus import PrometheusQueryClient
from app.observability.recorder import MetricsRecorder
from app.observability.runtime import get_process_observability
from app.observability.server import MetricsRuntime
from app.observability.service import ObservabilityReadService
from app.publications.service import DispatchPublicationService
from app.reviews.service import ReviewDecisionService
from app.runtime import build_runtime_graph, build_shared_memory_service
from app.runtime_overrides.checkpoint_updater import LangGraphStateUpdater
from app.runtime_overrides.events import RuntimeOverrideEventPublisher
from app.runtime_overrides.policy import RuntimeOverridePolicy
from app.runtime_overrides.query_service import RuntimeOverrideQueryService
from app.runtime_overrides.redis_lock import RuntimeBoundaryLock
from app.runtime_overrides.service import RuntimeOverrideService
from app.runtime_overrides.sqlalchemy_repository import SqlAlchemyRuntimeOverrideRepository
from app.runtime_threads.checkpoint_store import RedisRuntimeCheckpointStore
from app.runtime_threads.service import ThreadStateService
from app.runtime_threads.sqlalchemy_repository import SqlAlchemyRuntimeThreadRepository
from app.security.authentication import DisabledAuthenticationProvider
from app.security.demo_employee_accounts import (
    DemoEmployeeSessionService,
    SqlAlchemyDemoEmployeeAccountRepository,
)
from app.security.development_session import DevelopmentSessionIssuer
from app.security.errors import SecurityHttpError
from app.security.http import JsonBodyLimitMiddleware, SecurityHeadersMiddleware
from app.security.jwt_provider import DevelopmentJwtProvider, HttpJwksKeyResolver, OidcJwtProvider
from app.security.protocols import AuthenticationProvider
from app.security.rate_limit import (
    EmergencyReadRateLimiter,
    RateLimitAdmission,
    RedisTokenBucketRateLimiter,
    policies_from_settings,
)
from app.security.revocation import RedisRevocationStore
from app.security.security_audit import SecurityAuditRecorder
from app.security.sqlalchemy_audit_repository import SqlAlchemySecurityAuditRepository
from app.security.ws_ticket import RedisWsTicketService
from app.services.dispatch_task_api_service import DispatchTaskApiService
from app.streams.redis_queue import RedisStreamQueue
from app.vehicle_operations.progressor import VehicleOperationsProgressor
from app.vehicle_operations.query_service import SystemClock, VehicleOperationsQueryService
from app.vehicle_operations.sqlalchemy_repository import SqlAlchemyVehicleOperationsRepository
from app.workspace_reads.qdrant_repository import QdrantVectorMemoryReadRepository
from app.workspace_reads.service import WorkspaceReadService
from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository


def create_app(
    *,
    runtime_override_service: object | None = None,
    runtime_override_query_service: object | None = None,
    metrics_recorder: MetricsRecorder | None = None,
    metrics_runtime: MetricsRuntime | None = None,
    observability_service: object | None = None,
    anomaly_report_service: AnomalyReportService | None = None,
    authentication_provider: AuthenticationProvider | None = None,
    revocation_store: object | None = None,
    security_audit_repository: object | None = None,
    shared_memory_service: object | None = None,
    rate_limiter: object | None = None,
    workspace_read_service: WorkspaceReadService | None = None,
    demo_employee_service: DemoEmployeeSessionService | None = None,
    review_decision_service: ReviewDecisionService | None = None,
    dispatch_publication_service: DispatchPublicationService | None = None,
    vehicle_operations_api_service: object | None = None,
    demo_scenario_reset_service: DemoScenarioResetService | None = None,
) -> FastAPI:
    settings = get_settings()
    production = settings.runtime_profile == "production"
    app = FastAPI(
        title="CountyFlow AI",
        version="0.1.0",
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )
    app.state.runtime_profile = settings.runtime_profile
    app.state.development_session_issuer = None
    app.state.demo_employee_service = None
    if settings.runtime_profile in {"local", "docker-dev", "test"} and settings.authentication_provider == "development_jwt":
        development_session_issuer = DevelopmentSessionIssuer(
            settings.development_jwt_secret.get_secret_value(),
            issuer=settings.auth_issuer,
            audience=settings.auth_audience,
            ttl_seconds=settings.auth_access_token_ttl_seconds,
        )
        app.state.development_session_issuer = development_session_issuer
        app.state.demo_employee_service = demo_employee_service or DemoEmployeeSessionService(
            SqlAlchemyDemoEmployeeAccountRepository(build_session_factory(settings.database_url)),
            development_session_issuer,
        )
    if settings.runtime_profile in {"docker-dev", "production"}:
        configure_structured_logging("backend", settings.runtime_profile)
    process_observability = get_process_observability(settings.metrics_enabled, settings.metrics_host, settings.metrics_port)
    app.state.metrics_recorder = metrics_recorder or process_observability.recorder
    app.state.metrics_runtime = metrics_runtime or process_observability.runtime
    app.add_middleware(MetricsMiddleware, recorder=app.state.metrics_recorder)
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(
        JsonBodyLimitMiddleware,
        default_limit_bytes=settings.request_body_default_max_bytes,
        route_limits={
            ("POST", "/api/v1/dispatch-tasks"): settings.request_body_dispatch_max_bytes,
            ("POST", "/api/v1/anomaly-reports"): settings.request_body_dispatch_max_bytes,
            ("POST", "/api/v1/runtime/threads/*/overrides"): settings.request_body_runtime_override_max_bytes,
            ("POST", "/api/v1/memory/mutations"): settings.request_body_memory_mutation_max_bytes,
            ("POST", "/api/v1/ws-tickets"): settings.request_body_ws_ticket_max_bytes,
        },
    )
    app.add_middleware(
        SecurityHeadersMiddleware,
        runtime_profile=settings.runtime_profile,
        hsts_enabled=settings.security_hsts_enabled,
        oidc_issuer=settings.auth_issuer,
    )

    @app.on_event("startup")
    async def start_metrics_runtime() -> None:
        app.state.metrics_runtime.start()

    @app.on_event("shutdown")
    async def stop_metrics_runtime() -> None:
        app.state.metrics_runtime.stop()

    if settings.metrics_enabled:
        app.state.backend_observability_runtime = build_backend_observability_runtime(settings, app.state.metrics_recorder)

        @app.on_event("startup")
        async def start_backend_observability() -> None:
            app.state.backend_observability_runtime.start()

        @app.on_event("shutdown")
        async def stop_backend_observability() -> None:
            await app.state.backend_observability_runtime.stop()

    client = Redis.from_url(settings.redis_url, decode_responses=False)
    app.state.ws_ticket_service = RedisWsTicketService(
        client,
        namespace=settings.ws_ticket_namespace,
        ttl_seconds=settings.ws_ticket_ttl_seconds,
    )
    rate_limit_policies = policies_from_settings(settings)
    app.state.rate_limit_admission = RateLimitAdmission(
        rate_limiter
        or RedisTokenBucketRateLimiter(
            client,
            rate_limit_policies,
            namespace=settings.rate_limit_namespace,
        ),
        rate_limit_policies,
        emergency_reads=EmergencyReadRateLimiter(
            capacity=settings.rate_limit_emergency_read_capacity,
            window_seconds=settings.rate_limit_emergency_read_window_seconds,
        ),
    )
    app.state.revocation_store = revocation_store or RedisRevocationStore(
        client,
        namespace=settings.auth_revocation_namespace,
    )
    if authentication_provider is None:
        if settings.authentication_provider == "development_jwt":
            authentication_provider = DevelopmentJwtProvider(
                settings.development_jwt_secret.get_secret_value(),
                issuer=settings.auth_issuer,
                audience=settings.auth_audience,
                revocations=app.state.revocation_store,
                leeway_seconds=settings.auth_clock_skew_seconds,
            )
        elif settings.authentication_provider == "oidc_jwt":
            authentication_provider = OidcJwtProvider(
                HttpJwksKeyResolver(settings.auth_jwks_url),
                issuer=settings.auth_issuer,
                audience=settings.auth_audience,
                algorithms=tuple(value.strip() for value in settings.auth_algorithms.split(",") if value.strip()),
                revocations=app.state.revocation_store,
                leeway_seconds=settings.auth_clock_skew_seconds,
            )
        else:
            authentication_provider = DisabledAuthenticationProvider()
    app.state.authentication_provider = authentication_provider
    app.include_router(auth_router)
    app.include_router(ws_tickets_router)
    workspace_qdrant_client: QdrantClient | None = None
    if workspace_read_service is None:
        workspace_qdrant_client = QdrantClient(settings.qdrant_url)
        workspace_read_service = WorkspaceReadService(
            SqlAlchemyWorkspaceReadRepository(build_session_factory(settings.database_url)),
            QdrantVectorMemoryReadRepository(workspace_qdrant_client, "entity_resolution_memory"),
        )
    app.state.workspace_read_service = workspace_read_service
    app.include_router(workspace_reads_router)

    vehicle_operations_progressor = None
    if vehicle_operations_api_service is None:
        vehicle_operations_session_factory = build_session_factory(settings.database_url)
        vehicle_operations_repository = SqlAlchemyVehicleOperationsRepository(vehicle_operations_session_factory)
        vehicle_operations_api_service = VehicleOperationsQueryService(
            vehicle_operations_session_factory,
            vehicle_operations_repository,
        )
        if settings.runtime_profile in {"local", "docker-dev"}:
            vehicle_operations_progressor = VehicleOperationsProgressor(
                vehicle_operations_repository,
                SystemClock(),
            )
    app.state.vehicle_operations_api_service = vehicle_operations_api_service
    app.include_router(vehicle_operations_router)
    if vehicle_operations_progressor is not None:
        app.state.vehicle_operations_progressor_task = None

        @app.on_event("startup")
        async def start_vehicle_operations_progressor() -> None:
            bind = vehicle_operations_session_factory.kw.get("bind")
            inspector = inspect(bind)
            if not inspector.has_table("rescue_missions") or not inspector.has_table("maintenance_orders"):
                return
            app.state.vehicle_operations_progressor_task = asyncio.create_task(vehicle_operations_progressor.run_forever())

        @app.on_event("shutdown")
        async def stop_vehicle_operations_progressor() -> None:
            if app.state.vehicle_operations_progressor_task is None:
                return
            await vehicle_operations_progressor.shutdown()
            await app.state.vehicle_operations_progressor_task

    app.state.review_decision_service = review_decision_service or ReviewDecisionService(build_session_factory(settings.database_url))
    app.include_router(review_decisions_router)

    if workspace_qdrant_client is not None:

        @app.on_event("shutdown")
        async def close_workspace_qdrant_client() -> None:
            workspace_qdrant_client.close()

    app.state.security_audit_repository = security_audit_repository or SqlAlchemySecurityAuditRepository(build_session_factory(settings.database_url))
    app.state.security_audit_recorder = SecurityAuditRecorder(app.state.security_audit_repository)
    app.include_router(security_audit_router)
    queue = RedisStreamQueue(
        client, settings.redis_stream_name, settings.redis_consumer_group, settings.redis_consumer_name, dlq_stream_name=settings.redis_dlq_stream_name
    )
    event_client = Redis.from_url(settings.redis_url, decode_responses=False)
    app.state.task_event_broker = create_task_event_broker(settings, event_client)
    dispatch_session_factory = build_session_factory(settings.database_url)
    app.state.dispatch_task_api_service = DispatchTaskApiService(
        dispatch_session_factory,
        queue,
        event_broker=app.state.task_event_broker,
    )
    app.state.anomaly_report_service = anomaly_report_service or AnomalyReportService(
        SqlAlchemyAnomalyReportRepository(dispatch_session_factory),
        app.state.dispatch_task_api_service,
    )
    app.state.demo_scenario_reset_service = demo_scenario_reset_service or DemoScenarioResetService(
        dispatch_session_factory
    )
    app.state.dispatch_publication_service = dispatch_publication_service or DispatchPublicationService(build_session_factory(settings.database_url))
    app.include_router(dispatch_tasks_router)
    app.include_router(anomaly_reports_router)
    app.include_router(demo_scenarios_router)
    app.include_router(task_events_router)
    if settings.observability_api_enabled or observability_service is not None:
        app.state.observability_service = observability_service or ObservabilityReadService(
            PrometheusQueryClient(settings.prometheus_url),
            grafana_url=settings.grafana_public_url or None,
        )
        app.include_router(observability_router)
    if settings.runtime_thread_api_enabled:
        runtime_thread_redis = Redis.from_url(settings.redis_url, decode_responses=False)
        runtime_thread_store = RedisRuntimeCheckpointStore.from_redis_client(
            runtime_thread_redis,
            ttl_minutes=settings.runtime_checkpoint_retention_minutes,
            refresh_on_read=settings.runtime_checkpoint_refresh_on_read,
            namespace=settings.runtime_checkpoint_namespace,
        )
        app.state.runtime_thread_service = ThreadStateService(
            SqlAlchemyRuntimeThreadRepository(build_session_factory(settings.database_url)),
            runtime_thread_store,
            history_max_limit=settings.runtime_thread_history_max_limit,
        )
        app.include_router(runtime_threads_router)

        @app.on_event("startup")
        async def setup_runtime_thread_store() -> None:
            await runtime_thread_store.setup()

        @app.on_event("shutdown")
        async def close_runtime_thread_store() -> None:
            await runtime_thread_store.close()
            await runtime_thread_redis.aclose()

    if settings.runtime_override_api_enabled or runtime_override_service is not None:
        override_resources: tuple[object, ...] = ()
        if runtime_override_service is None:
            override_redis = Redis.from_url(settings.redis_url, decode_responses=False)
            override_store = RedisRuntimeCheckpointStore.from_redis_client(
                override_redis,
                ttl_minutes=settings.runtime_checkpoint_retention_minutes,
                refresh_on_read=settings.runtime_checkpoint_refresh_on_read,
                namespace=settings.runtime_checkpoint_namespace,
                metrics=app.state.metrics_recorder,
            )
            override_qdrant = QdrantClient(settings.qdrant_url)
            override_neo4j = build_neo4j_driver(settings)
            override_graph = build_runtime_graph(
                settings,
                override_qdrant,
                override_neo4j,
                checkpointer=override_store.native_checkpointer,
                metrics=app.state.metrics_recorder,
            )
            session_factory = build_session_factory(settings.database_url)
            override_repository = SqlAlchemyRuntimeOverrideRepository(session_factory)
            override_thread_repository = SqlAlchemyRuntimeThreadRepository(session_factory)
            override_event_publisher = RuntimeOverrideEventPublisher(app.state.task_event_broker)
            app.state.runtime_override_event_publisher = override_event_publisher
            runtime_override_service = RuntimeOverrideService(
                override_repository,
                override_thread_repository,
                override_store,
                LangGraphStateUpdater(
                    override_graph,
                    override_store,
                    max_checkpoint_bytes=settings.runtime_checkpoint_max_bytes,
                ),
                RuntimeOverridePolicy(),
                RuntimeBoundaryLock(override_redis, ttl_ms=settings.runtime_override_lock_ttl_ms),
                event_publisher=override_event_publisher,
                metrics=app.state.metrics_recorder,
            )
            runtime_override_query_service = RuntimeOverrideQueryService(
                override_repository,
                override_thread_repository,
                override_store,
            )
            override_resources = (override_store, override_redis, override_qdrant, override_neo4j)
        if runtime_override_query_service is None:
            raise RuntimeError("Runtime override API requires an injected query service.")
        app.state.runtime_override_service = runtime_override_service
        app.state.runtime_override_query_service = runtime_override_query_service
        app.include_router(runtime_overrides_router)

        if override_resources:

            @app.on_event("startup")
            async def setup_runtime_override_store() -> None:
                await override_resources[0].setup()

            @app.on_event("shutdown")
            async def close_runtime_override_resources() -> None:
                await override_resources[0].close()
                await override_resources[1].aclose()
                override_resources[2].close()
                if override_resources[3] is not None:
                    await override_resources[3].close()

    if settings.memory_mutation_api_enabled or shared_memory_service is not None:
        memory_resources: tuple[object, ...] = ()
        if shared_memory_service is None:
            qdrant_client = QdrantClient(settings.qdrant_url)
            neo4j_driver = build_neo4j_driver(settings)
            if neo4j_driver is None:
                raise RuntimeError("Shared Memory requires the configured Neo4j backend.")
            app.state.shared_memory_qdrant_client = qdrant_client
            app.state.shared_memory_neo4j_driver = neo4j_driver
            shared_memory_service = build_shared_memory_service(
                settings,
                client,
                qdrant_client,
                neo4j_driver,
                app.state.task_event_broker,
                app.state.metrics_recorder,
            )
            memory_resources = (qdrant_client, neo4j_driver)
        app.state.shared_memory_service = shared_memory_service
        app.include_router(memory_mutations_router)

        if memory_resources:

            @app.on_event("shutdown")
            async def close_shared_memory_resources() -> None:
                memory_resources[0].close()
                await memory_resources[1].close()

    @app.exception_handler(OptimisticLockConflict)
    async def optimistic_lock_handler(_: Request, error: OptimisticLockConflict) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "code": "DISPATCH_VERSION_CONFLICT",
                "message": str(error),
                "details": {"dispatch_id": error.dispatch_id},
            },
        )

    @app.exception_handler(SecurityHttpError)
    async def security_error_handler(_: Request, error: SecurityHttpError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"code": error.code, "message": error.message},
            headers=error.headers,
        )

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": "countyflow-backend",
            "version": "0.1.0",
            "runtime": settings.runtime_summary(),
        }

    return app


app = create_app()
