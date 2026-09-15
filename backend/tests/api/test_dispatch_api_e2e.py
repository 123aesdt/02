import asyncio
from dataclasses import replace

from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient
from security_support import authorize_app, principal_for
from sqlalchemy import func, select

from app.anomaly_reports.service import AnomalyReportService
from app.anomaly_reports.sqlalchemy_repository import SqlAlchemyAnomalyReportRepository
from app.audit.service import AuditService
from app.capacity.models import CapacitySnapshot
from app.capacity.provider import InMemoryCapacityProvider
from app.capacity.service import CapacityService
from app.dispatch.service import DispatchService
from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.idempotency.service import IdempotencyService
from app.locks.redis_execution_lock import RedisExecutionLock
from app.main import create_app
from app.models.audit import AuditRecord
from app.models.dispatch import Dispatch
from app.models.task import DispatchTask
from app.providers.environment import EnvironmentResult, StaticRouteFallbackProvider
from app.publications.service import DispatchPublicationService
from app.real_routes.service import RealRoadRouteService
from app.security.dependencies import get_current_principal
from app.security.permissions import Role
from app.seed import seed_demo_employee_accounts
from app.services.circuit_breaker import CircuitBreaker
from app.services.dispatch_task_api_service import DispatchTaskApiService
from app.services.environment import EnvironmentService
from app.streams.redis_queue import RedisStreamQueue
from app.workers.dispatch_worker import DispatchWorker
from tests.graph.test_routing_agent import _memory_service, _routing_service
from tests.unit.test_dispatch_service import _service


class _RainEnvironmentProvider:
    async def get_environment(self, route_id: str) -> EnvironmentResult:
        return EnvironmentResult("heavy_rain", "slippery", "high", "test_environment", False, None, 1.0)


async def _seven_agent_graph(factory):
    return build_graph(
        GraphDependencies(
            entity_memory_service=await _memory_service(),
            environment_service=EnvironmentService(
                _RainEnvironmentProvider(),
                StaticRouteFallbackProvider(),
                CircuitBreaker(3, 5.0),
            ),
            capacity_service=CapacityService(
                InMemoryCapacityProvider({("driver-li", "vehicle-001"): CapacitySnapshot(True, True, 0.45, 0.60, "e2e_capacity")}),
                limited_threshold=0.8,
                unavailable_threshold=1.0,
            ),
            routing_service=_routing_service(),
            dispatch_service=DispatchService(factory),
            audit_service=AuditService(factory),
        )
    )


def test_openapi_contains_dispatch_task_routes():
    app = create_app()
    schema = TestClient(app).get("/openapi.json").json()

    paths = schema["paths"]
    assert set(paths["/api/v1/dispatch-tasks"]) == {"post"}
    assert set(paths["/api/v1/dispatch-tasks/{task_id}"]) == {"get"}
    assert set(paths["/api/v1/dispatch-tasks/{task_id}/result"]) == {"get"}
    assert "$ref" in paths["/api/v1/dispatch-tasks"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert "$ref" in paths["/api/v1/dispatch-tasks"]["post"]["responses"]["202"]["content"]["application/json"]["schema"]
    assert "$ref" in paths["/api/v1/dispatch-tasks/{task_id}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert "$ref" in paths["/api/v1/dispatch-tasks/{task_id}/result"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]


def test_docs_contains_dispatch_task_operations():
    app = create_app()
    response = TestClient(app).get("/docs")

    assert response.status_code == 200
    assert "swagger-ui" in response.text.lower()
    assert "/openapi.json" in response.text


def test_dispatch_api_end_to_end():
    temp, engine, factory = _service()
    redis = FakeRedis(decode_responses=False)
    stream_name = "countyflow:e2e:tasks"
    group_name = "countyflow-e2e-workers"
    try:
        app = authorize_app(create_app())
        api_queue = RedisStreamQueue(redis, stream_name, group_name, "api-e2e")
        app.state.dispatch_task_api_service = DispatchTaskApiService(factory, api_queue)
        client = TestClient(app)
        payload = {
            "order_id": 1,
            "driver_id": "driver-li",
            "vehicle_id": "vehicle-001",
            "route_id": "xinping-road",
            "anomaly_type": "rain_slippery",
            "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
            "idempotency_key": "dispatch-e2e-001",
        }

        created = client.post("/api/v1/dispatch-tasks", json=payload)
        replay = client.post("/api/v1/dispatch-tasks", json=payload)
        task_id = created.json()["task_id"]
        before_status = client.get(f"/api/v1/dispatch-tasks/{task_id}")
        before_result = client.get(f"/api/v1/dispatch-tasks/{task_id}/result")

        worker_queue = RedisStreamQueue(redis, stream_name, group_name, "worker-e2e")
        worker = DispatchWorker(
            worker_queue,
            asyncio.run(_seven_agent_graph(factory)),
            read_count=1,
            block_ms=1,
            consumer_name="worker-e2e",
            idempotency_service=IdempotencyService(factory),
            execution_lock=RedisExecutionLock(redis, ttl_ms=1_000),
        )
        [worker_result] = asyncio.run(worker.run_once())
        pending = asyncio.run(redis.xpending(stream_name, group_name))
        after_status = client.get(f"/api/v1/dispatch-tasks/{task_id}")
        after_result = client.get(f"/api/v1/dispatch-tasks/{task_id}/result")

        with factory() as session:
            dispatch = session.scalar(select(Dispatch).where(Dispatch.task_id.is_not(None)))
            audit = session.scalar(select(AuditRecord).where(AuditRecord.dispatch_id == dispatch.id))
            dispatch_count = session.scalar(select(func.count()).select_from(Dispatch))
            audit_count = session.scalar(select(func.count()).select_from(AuditRecord))

        assert created.status_code == replay.status_code == 202
        assert replay.json()["task_id"] == task_id
        assert replay.json()["duplicate"] is True
        assert len(asyncio.run(redis.xrange(stream_name))) == 1
        assert (before_status.status_code, before_status.json()["status"]) == (200, "PENDING")
        assert (before_result.status_code, before_result.json()["ready"]) == (202, False)
        assert (worker_result.acknowledged, worker_result.terminal_status) == (True, "APPROVED")
        assert pending["pending"] == 0
        assert (after_status.status_code, after_status.json()["status"]) == (200, "COMPLETED")
        assert (after_result.status_code, after_result.json()["ready"]) == (200, True)
        assert after_result.json()["dispatch"]["target_route_id"] == "national-102"
        assert after_result.json()["audit"]["result"] == "APPROVED"
        assert (dispatch.original_route_id, dispatch.target_route_id) == ("xinping-road", "national-102")
        assert audit.result == "APPROVED"
        assert (dispatch_count, audit_count) == (1, 1)
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_sandtable_breakdown_result_uses_persisted_fleet_and_complete_route_snapshot() -> None:
    from app.capacity.provider import FleetCapacityProvider
    from app.fleet.service import DijkstraTravelTimeEstimator, FleetAllocationService
    from app.fleet.sqlalchemy_repository import SqlAlchemyFleetRepository
    from app.models.order import Order
    from app.road_network.dijkstra import DijkstraPathFinder
    from app.road_network.service import RoadNetworkSnapshotService
    from app.road_network.sqlalchemy_repository import SqlAlchemyRoadNetworkRepository
    from app.routing.service import RoutingService
    from app.sandtable.seed_data import ROAD_EDGES, ROAD_NODES, VEHICLES
    from app.sandtable.service import SandtableContextService
    from app.sandtable.sqlalchemy_repository import SqlAlchemySandtableRepository, seed_new_county_sandtable

    temp, engine, factory = _service()
    redis = FakeRedis(decode_responses=False)
    stream_name = "countyflow:e2e:sandtable:tasks"
    group_name = "countyflow-e2e-sandtable-workers"
    try:
        with factory() as session:
            seed_new_county_sandtable(session)
            order = session.execute(select(Order).where(Order.order_no == "DEMO-ORDER-001")).scalar_one()
            order_id = order.id

        road_repository = SqlAlchemyRoadNetworkRepository(factory)
        fleet_repository = SqlAlchemyFleetRepository(factory)
        path_finder = DijkstraPathFinder()
        graph = build_graph(
            GraphDependencies(
                capacity_service=CapacityService(
                    FleetCapacityProvider(fleet_repository),
                    limited_threshold=0.8,
                    unavailable_threshold=1.0,
                ),
                sandtable_context_service=SandtableContextService(SqlAlchemySandtableRepository(factory)),
                road_network_snapshot_service=RoadNetworkSnapshotService(road_repository),
                fleet_allocation_service=FleetAllocationService(
                    fleet_repository,
                    DijkstraTravelTimeEstimator(road_repository, path_finder),
                ),
                routing_service=RoutingService(
                    None,
                    memory_adoption_threshold=0.75,
                    road_network_provider=road_repository,
                    path_finder=path_finder,
                ),
                dispatch_service=DispatchService(factory),
                audit_service=AuditService(factory),
            )
        )
        app = authorize_app(create_app())
        app.state.dispatch_task_api_service = DispatchTaskApiService(
            factory,
            RedisStreamQueue(redis, stream_name, group_name, "api-sandtable-e2e"),
        )
        client = TestClient(app)
        created = client.post(
            "/api/v1/dispatch-tasks",
            json={
                "order_id": order_id,
                "driver_id": "D-001",
                "vehicle_id": "V-001",
                "vehicle_status": "BROKEN",
                "route_id": "xinping-road",
                "anomaly_type": "VEHICLE_BREAKDOWN",
                "anomaly_description": "新物冷链-01 在新平路 K3.2 发动机故障，无法继续配送。",
                "idempotency_key": "dispatch-e2e-sandtable-breakdown-001",
            },
        )
        task_id = created.json()["task_id"]
        worker = DispatchWorker(
            RedisStreamQueue(redis, stream_name, group_name, "worker-sandtable-e2e"),
            graph,
            read_count=1,
            block_ms=1,
            consumer_name="worker-sandtable-e2e",
            idempotency_service=IdempotencyService(factory),
            execution_lock=RedisExecutionLock(redis, ttl_ms=1_000),
        )

        [worker_result] = asyncio.run(worker.run_once())
        response = client.get(f"/api/v1/dispatch-tasks/{task_id}/result")
        body = response.json()

        assert created.status_code == 202
        assert (worker_result.acknowledged, worker_result.terminal_status) == (True, "APPROVED")
        assert response.status_code == 200
        assert body["vehicle_allocation"]["target_vehicle_id"] == "V-005"
        assert body["vehicle_allocation"]["target_driver_id"] == "D-003"
        assert body["vehicle_allocation"]["pickup_route"]["edge_ids"] == ["E20"]
        assert len(body["vehicle_allocation"]["candidate_vehicles"]) == len(VEHICLES)
        assert body["route_plan"]["algorithm"] == "DIJKSTRA_V1"
        assert len(body["route_plan"]["network_nodes"]) == len(ROAD_NODES)
        assert len(body["route_plan"]["network_edges"]) == len(ROAD_EDGES)

        with factory() as session:
            blocked_order = session.execute(select(Order).where(Order.order_no == "DEMO-ORDER-005")).scalar_one()
            blocked_order_id = blocked_order.id
        blocked_created = client.post(
            "/api/v1/dispatch-tasks",
            json={
                "order_id": blocked_order_id,
                "driver_id": "D-007",
                "vehicle_id": "V-008",
                "route_id": "xinping-road",
                "anomaly_type": "ROAD_BLOCKED",
                "anomaly_description": "新平路东河桥段发生塌方，车辆无法通行。",
                "idempotency_key": "dispatch-e2e-sandtable-road-blocked-005",
            },
        )
        [blocked_worker_result] = asyncio.run(worker.run_once())
        blocked_response = client.get(f"/api/v1/dispatch-tasks/{blocked_created.json()['task_id']}/result")
        blocked_plan = blocked_response.json()["route_plan"]

        assert blocked_created.status_code == 202
        assert (
            blocked_worker_result.acknowledged,
            blocked_worker_result.terminal_status,
        ) == (True, "APPROVED")
        assert blocked_response.status_code == 200
        assert blocked_plan["distance_delta_km"] == "3.20"
        assert blocked_plan["eta_delta_minutes"] == 4
        assert blocked_plan["blocked_edge_ids"] == ["E04"]
        assert blocked_plan["recommended_path"]["edge_ids"] == [
            "E01",
            "E06",
            "E07",
            "E08",
            "E09",
        ]
        assert "E04" not in blocked_plan["recommended_path"]["edge_ids"]
        assert len(blocked_plan["network_nodes"]) == len(ROAD_NODES)
        assert len(blocked_plan["network_edges"]) == len(ROAD_EDGES)
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_employee_road_block_report_is_rerouted_published_and_acknowledged() -> None:
    from app.capacity.provider import FleetCapacityProvider
    from app.fleet.service import DijkstraTravelTimeEstimator, FleetAllocationService
    from app.fleet.sqlalchemy_repository import SqlAlchemyFleetRepository
    from app.models.order import Order
    from app.road_network.dijkstra import DijkstraPathFinder
    from app.road_network.service import RoadNetworkSnapshotService
    from app.road_network.sqlalchemy_repository import SqlAlchemyRoadNetworkRepository
    from app.routing.service import RoutingService
    from app.sandtable.service import SandtableContextService
    from app.sandtable.sqlalchemy_repository import SqlAlchemySandtableRepository, seed_new_county_sandtable

    temp, engine, factory = _service()
    redis = FakeRedis(decode_responses=False)
    stream_name = "countyflow:e2e:road-report:tasks"
    group_name = "countyflow-e2e-road-report-workers"
    dlq_name = "countyflow:e2e:road-report:dlq"
    try:
        with factory() as session:
            seed_new_county_sandtable(session)
            seed_demo_employee_accounts(session)
            order = session.execute(select(Order).where(Order.order_no == "DEMO-ORDER-005")).scalar_one()
            source_task = DispatchTask(
                task_id="TASK-ROAD-REPORT-SOURCE",
                order_id=order.id,
                status="IN_PROGRESS",
                idempotency_key="road-report-source-001",
                assignee_subject_id="CF-DEMO-001",
            )
            session.add(source_task)
            session.commit()

        api_queue = RedisStreamQueue(
            redis,
            stream_name,
            group_name,
            "api-road-report-e2e",
            dlq_stream_name=dlq_name,
        )
        dispatch_api = DispatchTaskApiService(factory, api_queue)
        publication_service = DispatchPublicationService(factory)
        report_service = AnomalyReportService(
            SqlAlchemyAnomalyReportRepository(factory),
            dispatch_api,
        )
        employee = replace(
            principal_for(Role.EMPLOYEE),
            subject_id="CF-DEMO-001",
            display_name="张师傅",
        )
        app = authorize_app(
            create_app(
                anomaly_report_service=report_service,
                dispatch_publication_service=publication_service,
            ),
            Role.EMPLOYEE,
        )
        app.dependency_overrides[get_current_principal] = lambda: employee
        app.state.dispatch_task_api_service = dispatch_api
        client = TestClient(app)

        reported = client.post(
            "/api/v1/anomaly-reports",
            json={
                "source_task_id": "TASK-ROAD-REPORT-SOURCE",
                "anomaly_type": "ROAD_BLOCKED",
                "description": "新平路东河桥段发生塌方，车辆无法通行。",
                "location_text": "新平路东河桥段",
                "reported_vehicle_status": "NORMAL",
                "severity": "HIGH",
                "incident_node_id": None,
                "affected_edge_id": "E04",
                "idempotency_key": "road-report-e2e-001",
            },
        )
        task_id = reported.json()["task_id"]

        road_repository = SqlAlchemyRoadNetworkRepository(factory)
        fleet_repository = SqlAlchemyFleetRepository(factory)
        path_finder = DijkstraPathFinder()
        graph = build_graph(
            GraphDependencies(
                capacity_service=CapacityService(
                    FleetCapacityProvider(fleet_repository),
                    limited_threshold=0.8,
                    unavailable_threshold=1.0,
                ),
                sandtable_context_service=SandtableContextService(SqlAlchemySandtableRepository(factory)),
                road_network_snapshot_service=RoadNetworkSnapshotService(road_repository),
                fleet_allocation_service=FleetAllocationService(
                    fleet_repository,
                    DijkstraTravelTimeEstimator(road_repository, path_finder),
                ),
                routing_service=RoutingService(
                    None,
                    memory_adoption_threshold=0.75,
                    road_network_provider=road_repository,
                    path_finder=path_finder,
                ),
                real_road_route_service=RealRoadRouteService(None),
                dispatch_service=DispatchService(factory),
                audit_service=AuditService(factory),
            )
        )
        worker = DispatchWorker(
            RedisStreamQueue(
                redis,
                stream_name,
                group_name,
                "worker-road-report-e2e",
                dlq_stream_name=dlq_name,
            ),
            graph,
            read_count=1,
            block_ms=1,
            consumer_name="worker-road-report-e2e",
            idempotency_service=IdempotencyService(factory),
            execution_lock=RedisExecutionLock(redis, ttl_ms=1_000),
            automatic_publication_service=publication_service,
        )

        [worker_result] = asyncio.run(worker.run_once())
        result = client.get(f"/api/v1/dispatch-tasks/{task_id}/result")
        body = result.json()

        assert reported.status_code == 202
        assert (worker_result.acknowledged, worker_result.terminal_status) == (True, "APPROVED")
        assert asyncio.run(redis.xlen(dlq_name)) == 0
        assert asyncio.run(redis.xpending(stream_name, group_name))["pending"] == 0
        assert result.status_code == 200
        assert body["status"] == "COMPLETED"
        assert body["audit"]["result"] == "APPROVED"
        assert body["publication"]["status"] == "PUBLISHED"
        assert body["publication"]["recipient_employee_id"] == "CF-DEMO-001"
        assert body["route_plan"]["blocked_edge_ids"] == ["E04"]
        assert body["route_plan"]["recommended_path"]["node_ids"]
        assert "E04" not in body["route_plan"]["recommended_path"]["edge_ids"]
        assert body["route_plan"]["real_road_route"]["provider"] == "AMAP"
        assert body["route_plan"]["real_road_route"]["status"] == "CLIENT_MATCH_REQUIRED"
        assert len(body["route_plan"]["real_road_route"]["waypoints"]) >= 2
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_openapi_exposes_strict_fleet_and_route_result_models() -> None:
    schema = TestClient(create_app()).get("/openapi.json").json()
    components = schema["components"]["schemas"]

    assert {
        "VehicleCandidateResponse",
        "VehicleAllocationResponse",
        "RoadNodeResponse",
        "RoadEdgeResponse",
        "PathResponse",
        "RouteCandidateResponse",
        "RoutePlanResponse",
    }.issubset(components)
    task_result = components["TaskResultResponse"]["properties"]
    assert "VehicleAllocationResponse" in str(task_result["vehicle_allocation"])
    assert "RoutePlanResponse" in str(task_result["route_plan"])
