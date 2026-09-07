import asyncio

from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient
from security_support import authorize_app, ws_ticket_url
from sqlalchemy import select

from app.events.broker import InMemoryTaskEventBroker
from app.events.models import TaskEvent, TaskEventType
from app.idempotency.service import IdempotencyService
from app.locks.redis_execution_lock import RedisExecutionLock
from app.main import create_app
from app.models.audit import AuditRecord
from app.models.dispatch import Dispatch
from app.services.dispatch_task_api_service import DispatchTaskApiService
from app.streams.redis_queue import RedisStreamQueue
from app.workers.dispatch_worker import DispatchWorker
from tests.unit.test_dispatch_service import _service
from tests.workers.test_worker_idempotency import _real_graph


def _app_with_events():
    app = authorize_app(create_app())
    temp, engine, factory = _service()
    redis = FakeRedis(decode_responses=False)
    broker = InMemoryTaskEventBroker()
    app.state.task_event_broker = broker
    app.state.dispatch_task_api_service = DispatchTaskApiService(
        factory,
        RedisStreamQueue(redis, "ws:tasks", "ws-workers", "ws-api"),
        event_broker=broker,
    )
    return app, temp, engine, redis, broker


def test_websocket_task_not_found():
    app, temp, engine, redis, _ = _app_with_events()
    try:
        with TestClient(app).websocket_connect(ws_ticket_url("/api/v1/ws/tasks/TASK-missing")) as socket:
            socket.receive_json()
    except Exception as error:
        assert getattr(error, "code", None) == 1008
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_websocket_sends_initial_snapshot():
    app, temp, engine, redis, _ = _app_with_events()
    try:
        with TestClient(app).websocket_connect(ws_ticket_url("/api/v1/ws/tasks/task-001")) as socket:
            snapshot = socket.receive_json()
        assert snapshot["event_type"] == "TASK_SNAPSHOT"
        assert snapshot["task_id"] == "task-001"
        assert snapshot["status"] == "created"
        assert snapshot["data"] == {"ready": False, "requires_manual_review": False}
        assert snapshot["sequence"] == 0
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_websocket_receives_task_events():
    app, temp, engine, redis, broker = _app_with_events()
    try:
        with TestClient(app).websocket_connect(ws_ticket_url("/api/v1/ws/tasks/task-001")) as socket:
            assert socket.receive_json()["event_type"] == "TASK_SNAPSHOT"
            asyncio.run(broker.publish(TaskEvent.create("task-001", TaskEventType.WORKER_STARTED, "worker", "PROCESSING")))
            assert socket.receive_json()["event_type"] == "WORKER_STARTED"
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_websocket_receives_terminal_event():
    app, temp, engine, redis, broker = _app_with_events()
    try:
        with TestClient(app).websocket_connect(ws_ticket_url("/api/v1/ws/tasks/task-001")) as socket:
            socket.receive_json()
            asyncio.run(broker.publish(TaskEvent.create("task-001", TaskEventType.TASK_COMPLETED, "audit", "COMPLETED")))
            assert socket.receive_json()["event_type"] == "TASK_COMPLETED"
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_websocket_disconnect_does_not_break_worker():
    app, temp, engine, redis, broker = _app_with_events()
    try:
        with TestClient(app).websocket_connect(ws_ticket_url("/api/v1/ws/tasks/task-001")) as socket:
            socket.receive_json()
        asyncio.run(broker.publish(TaskEvent.create("task-001", TaskEventType.WORKER_STARTED, "worker", "PROCESSING")))
        assert asyncio.run(broker.subscriber_count("task-001")) == 0
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_websocket_receives_worker_and_terminal_events_from_real_graph():
    app, temp, engine, redis, broker = _app_with_events()
    service = app.state.dispatch_task_api_service
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
                    "idempotency_key": "ws-e2e-001",
                },
            )
            task_id = created.json()["task_id"]
            worker = DispatchWorker(
                RedisStreamQueue(redis, "ws:tasks", "ws-workers", "ws-worker"),
                asyncio.run(_real_graph(service._session_factory)),
                read_count=1,
                block_ms=1,
                consumer_name="ws-worker",
                idempotency_service=IdempotencyService(service._session_factory),
                execution_lock=RedisExecutionLock(redis, ttl_ms=1_000),
                event_broker=broker,
            )
            with client.websocket_connect(ws_ticket_url(f"/api/v1/ws/tasks/{task_id}")) as socket:
                assert socket.receive_json()["event_type"] == "TASK_SNAPSHOT"
                asyncio.run(worker.run_once())
                event_types = [socket.receive_json()["event_type"] for _ in range(19)]

        with service._session_factory() as session:
            dispatch = session.scalar(select(Dispatch).where(Dispatch.task_id.is_not(None)))
            audit = session.scalar(select(AuditRecord).where(AuditRecord.dispatch_id == dispatch.id))

        assert created.status_code == 202
        assert event_types[0] == "TASK_ACCEPTED"
        assert {
            "WORKER_STARTED",
            "INTAKE_STARTED",
            "INTAKE_COMPLETED",
            "MEMORY_STARTED",
            "MEMORY_COMPLETED",
            "GRAPH_MEMORY_STARTED",
            "GRAPH_MEMORY_COMPLETED",
            "ENVIRONMENT_STARTED",
            "ENVIRONMENT_COMPLETED",
            "CAPACITY_STARTED",
            "CAPACITY_COMPLETED",
            "ROUTING_STARTED",
            "ROUTING_COMPLETED",
            "DISPATCH_STARTED",
            "DISPATCH_COMPLETED",
            "AUDIT_STARTED",
            "AUDIT_COMPLETED",
        }.issubset(event_types)
        assert event_types[-1] == "TASK_COMPLETED"
        assert (dispatch.target_route_id, audit.result) == ("national-102", "APPROVED")
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_websocket_preserves_extended_fleet_and_route_event_payloads() -> None:
    app, temp, engine, redis, broker = _app_with_events()
    try:
        with TestClient(app).websocket_connect(ws_ticket_url("/api/v1/ws/tasks/task-001")) as socket:
            assert socket.receive_json()["event_type"] == "TASK_SNAPSHOT"
            asyncio.run(
                broker.publish(
                    TaskEvent.create(
                        "task-001",
                        TaskEventType.CAPACITY_COMPLETED,
                        "capacity",
                        "PROCESSING",
                        data={
                            "vehicle_id": "V-001",
                            "capacity_status": "REASSIGNED",
                            "selected_vehicle_id": "V-005",
                            "selected_driver_id": "D-003",
                            "vehicle_reassigned": True,
                        },
                    )
                )
            )
            capacity = socket.receive_json()
            asyncio.run(
                broker.publish(
                    TaskEvent.create(
                        "task-001",
                        TaskEventType.ROUTING_COMPLETED,
                        "routing",
                        "PROCESSING",
                        data={
                            "algorithm": "DIJKSTRA_V1",
                            "blocked_edge_ids": ["E04"],
                            "recommended_path": {"edge_ids": ["E01", "E06", "E07", "E08", "E09"]},
                            "network_nodes": [],
                            "network_edges": [],
                        },
                    )
                )
            )
            routing = socket.receive_json()

        assert capacity["data"]["vehicle_id"] == "V-001"
        assert capacity["data"]["capacity_status"] == "REASSIGNED"
        assert capacity["data"]["selected_vehicle_id"] == "V-005"
        assert routing["data"]["algorithm"] == "DIJKSTRA_V1"
        assert routing["data"]["blocked_edge_ids"] == ["E04"]
        assert routing["data"]["recommended_path"]["edge_ids"] == [
            "E01",
            "E06",
            "E07",
            "E08",
            "E09",
        ]
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()
