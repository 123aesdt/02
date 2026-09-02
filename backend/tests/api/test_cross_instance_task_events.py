import asyncio

from fakeredis.aioredis import FakeRedis, FakeServer
from fastapi.testclient import TestClient
from httpx import AsyncClient, MockTransport, Response
from security_support import authorize_app, ws_ticket_url
from sqlalchemy import select

from app.events.broker import RedisTaskEventBroker
from app.events.models import TaskEvent, TaskEventType
from app.idempotency.service import IdempotencyService
from app.locks.redis_execution_lock import RedisExecutionLock
from app.main import create_app
from app.models.audit import AuditRecord
from app.models.dispatch import Dispatch
from app.providers.environment import HttpEnvironmentProvider, StaticRouteFallbackProvider
from app.services.circuit_breaker import CircuitBreaker
from app.services.dispatch_task_api_service import DispatchTaskApiService
from app.services.environment import EnvironmentService
from app.streams.redis_queue import RedisStreamQueue
from app.workers.dispatch_worker import DispatchWorker
from tests.graph.test_ai_core_final import _graph
from tests.unit.test_dispatch_service import _service
from tests.workers.test_worker_idempotency import _real_graph


def _cross_instance_app():
    server = FakeServer()
    api_client, worker_client, websocket_client = (FakeRedis(server=server, decode_responses=False) for _ in range(3))
    api_broker = RedisTaskEventBroker(api_client, "events", 100, read_block_ms=10)
    worker_broker = RedisTaskEventBroker(worker_client, "events", 100, read_block_ms=10)
    websocket_broker = RedisTaskEventBroker(websocket_client, "events", 100, read_block_ms=10)
    app = authorize_app(create_app())
    temp, engine, factory = _service()
    app.state.task_event_broker = websocket_broker
    app.state.dispatch_task_api_service = DispatchTaskApiService(
        factory,
        RedisStreamQueue(api_client, "tasks", "workers", "api"),
        event_broker=api_broker,
    )
    return app, temp, engine, factory, api_client, worker_client, websocket_client, api_broker, worker_broker, websocket_broker


def test_cross_instance_api_worker_websocket_events():
    app, temp, engine, factory, api_client, worker_client, websocket_client, api_broker, worker_broker, websocket_broker = _cross_instance_app()
    try:
        assert api_broker is not worker_broker and worker_broker is not websocket_broker and api_broker is not websocket_broker
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/dispatch-tasks",
                json={
                    "order_id": 1,
                    "driver_id": "driver-li",
                    "vehicle_id": "vehicle-001",
                    "route_id": "xinping-road",
                    "anomaly_type": "rain_slippery",
                    "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
                    "idempotency_key": "cross-001",
                },
            )
            task_id = created.json()["task_id"]
            worker = DispatchWorker(
                RedisStreamQueue(worker_client, "tasks", "workers", "worker"),
                asyncio.run(_real_graph(factory)),
                read_count=1,
                block_ms=1,
                consumer_name="worker",
                idempotency_service=IdempotencyService(factory),
                execution_lock=RedisExecutionLock(worker_client, ttl_ms=1000),
                event_broker=worker_broker,
            )
            with client.websocket_connect(ws_ticket_url(f"/api/v1/ws/tasks/{task_id}")) as socket:
                assert socket.receive_json()["event_type"] == "TASK_SNAPSHOT"
                asyncio.run(worker.run_once())
                events = [socket.receive_json() for _ in range(19)]
        with factory() as session:
            dispatch = session.scalar(select(Dispatch).where(Dispatch.task_id.is_not(None)))
            audit = session.scalar(select(AuditRecord).where(AuditRecord.dispatch_id == dispatch.id))
        pending = asyncio.run(worker_client.xpending("tasks", "workers"))
        routing = next(event for event in events if event["event_type"] == "ROUTING_COMPLETED")
        assert created.status_code == 202
        expected = {
            "TASK_ACCEPTED",
            "WORKER_STARTED",
            "INTAKE_STARTED",
            "INTAKE_COMPLETED",
            "MEMORY_STARTED",
            "MEMORY_COMPLETED",
            "GRAPH_MEMORY_STARTED",
            "GRAPH_MEMORY_COMPLETED",
            "ENVIRONMENT_COMPLETED",
            "CAPACITY_COMPLETED",
            "ROUTING_COMPLETED",
            "DISPATCH_COMPLETED",
            "AUDIT_COMPLETED",
            "TASK_COMPLETED",
        }
        assert expected.issubset({event["event_type"] for event in events})
        assert {
            key: routing["data"][key]
            for key in ("recommended_route", "decision", "memory_adopted", "adopted_memory_id")
        } == {
            "recommended_route": "national-102",
            "decision": "REROUTE",
            "memory_adopted": True,
            "adopted_memory_id": "memory-rain-li",
        }
        assert routing["data"]["requires_manual_review"] is False
        assert "memory-rain-li" in routing["data"]["decision_reason"]
        assert any(candidate["route_id"] == "national-102" for candidate in routing["data"]["candidate_routes"])
        assert [event["sequence"] for event in events] == sorted(event["sequence"] for event in events)
        assert (dispatch.target_route_id, audit.result, pending["pending"]) == ("national-102", "APPROVED", 0)
    finally:
        for client in (api_client, worker_client, websocket_client):
            asyncio.run(client.aclose())
        engine.dispose()
        temp.cleanup()


def test_websocket_last_event_id_replay_cross_instance():
    app, temp, engine, factory, api_client, worker_client, websocket_client, api_broker, worker_broker, websocket_broker = _cross_instance_app()
    try:
        first = asyncio.run(api_broker.publish(TaskEvent.create("task-001", TaskEventType.TASK_ACCEPTED, "api", "PENDING")))
        second = asyncio.run(worker_broker.publish(TaskEvent.create("task-001", TaskEventType.WORKER_STARTED, "worker", "PROCESSING")))
        third = asyncio.run(worker_broker.publish(TaskEvent.create("task-001", TaskEventType.ROUTING_COMPLETED, "routing", "PROCESSING")))
        with TestClient(app).websocket_connect(
            ws_ticket_url(f"/api/v1/ws/tasks/task-001?last_event_id={first.event_id}")
        ) as socket:
            snapshot, replay_second, replay_third = socket.receive_json(), socket.receive_json(), socket.receive_json()
            fourth = asyncio.run(api_broker.publish(TaskEvent.create("task-001", TaskEventType.TASK_COMPLETED, "audit", "COMPLETED")))
            live = socket.receive_json()
        assert snapshot["event_type"] == "TASK_SNAPSHOT"
        assert [replay_second["event_id"], replay_third["event_id"], live["event_id"]] == [second.event_id, third.event_id, fourth.event_id]
    finally:
        for client in (api_client, worker_client, websocket_client):
            asyncio.run(client.aclose())
        engine.dispose()
        temp.cleanup()


def test_websocket_disconnect_does_not_affect_worker_cross_instance():
    app, temp, engine, factory, api_client, worker_client, websocket_client, api_broker, worker_broker, websocket_broker = _cross_instance_app()
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/dispatch-tasks",
                json={
                    "order_id": 1,
                    "driver_id": "driver-li",
                    "vehicle_id": "vehicle-001",
                    "route_id": "xinping-road",
                    "anomaly_type": "rain_slippery",
                    "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
                    "idempotency_key": "disconnect-001",
                },
            )
            task_id = created.json()["task_id"]
            with client.websocket_connect(ws_ticket_url(f"/api/v1/ws/tasks/{task_id}")) as socket:
                assert socket.receive_json()["event_type"] == "TASK_SNAPSHOT"
            worker = DispatchWorker(
                RedisStreamQueue(worker_client, "tasks", "workers", "worker"),
                asyncio.run(_real_graph(factory)),
                read_count=1,
                block_ms=1,
                consumer_name="worker",
                idempotency_service=IdempotencyService(factory),
                execution_lock=RedisExecutionLock(worker_client, ttl_ms=1000),
                event_broker=worker_broker,
            )
            asyncio.run(worker.run_once())
        with factory() as session:
            dispatch = session.scalar(select(Dispatch).where(Dispatch.task_id.is_not(None)))
            audit = session.scalar(select(AuditRecord).where(AuditRecord.dispatch_id == dispatch.id))
        assert (dispatch.target_route_id, audit.result, asyncio.run(worker_client.xpending("tasks", "workers"))["pending"]) == (
            "national-102",
            "APPROVED",
            0,
        )
    finally:
        for client in (api_client, worker_client, websocket_client):
            asyncio.run(client.aclose())
        engine.dispose()
        temp.cleanup()


def test_environment_fallback_event_cross_instance():
    async def handler(request):
        await asyncio.sleep(2.0)
        return Response(200, json={})

    app, temp, engine, factory, api_client, worker_client, websocket_client, api_broker, worker_broker, websocket_broker = _cross_instance_app()
    environment_client = AsyncClient(transport=MockTransport(handler))
    try:
        environment = EnvironmentService(
            HttpEnvironmentProvider("https://environment.test", client=environment_client, timeout_seconds=0.8),
            StaticRouteFallbackProvider(),
            CircuitBreaker(3, 5.0),
        )
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/dispatch-tasks",
                json={
                    "order_id": 1,
                    "driver_id": "driver-li",
                    "vehicle_id": "vehicle-001",
                    "route_id": "xinping-road",
                    "anomaly_type": "rain_slippery",
                    "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
                    "idempotency_key": "fallback-001",
                },
            )
            task_id = created.json()["task_id"]
            worker = DispatchWorker(
                RedisStreamQueue(worker_client, "tasks", "workers", "worker"),
                asyncio.run(_graph(factory, environment)),
                read_count=1,
                block_ms=1,
                consumer_name="worker",
                idempotency_service=IdempotencyService(factory),
                execution_lock=RedisExecutionLock(worker_client, ttl_ms=1000),
                event_broker=worker_broker,
            )
            with client.websocket_connect(ws_ticket_url(f"/api/v1/ws/tasks/{task_id}")) as socket:
                socket.receive_json()
                asyncio.run(worker.run_once())
                events = [socket.receive_json() for _ in range(20)]
        fallback = next(event for event in events if event["event_type"] == "ENVIRONMENT_FALLBACK")
        assert fallback["data"]["fallback_reason"]
        assert fallback["data"]["environment_elapsed_ms"] < 1000
        assert fallback["data"]["environment_risk"]
        assert events[-1]["event_type"] == "TASK_COMPLETED"
        assert [event["sequence"] for event in events] == sorted(event["sequence"] for event in events)
    finally:
        asyncio.run(environment_client.aclose())
        for client in (api_client, worker_client, websocket_client):
            asyncio.run(client.aclose())
        engine.dispose()
        temp.cleanup()
