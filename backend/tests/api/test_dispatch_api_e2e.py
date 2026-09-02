import asyncio

from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient
from security_support import authorize_app
from sqlalchemy import func, select

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
from app.providers.environment import EnvironmentResult, StaticRouteFallbackProvider
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
                InMemoryCapacityProvider(
                    {("driver-li", "vehicle-001"): CapacitySnapshot(True, True, 0.45, 0.60, "e2e_capacity")}
                ),
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
