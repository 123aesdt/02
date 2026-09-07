import asyncio

from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient
from security_support import authorize_app, principal_for, ws_ticket_url
from sqlalchemy import select

from app.events.broker import InMemoryTaskEventBroker
from app.events.models import TaskEvent, TaskEventType
from app.idempotency.service import IdempotencyService
from app.locks.redis_execution_lock import RedisExecutionLock
from app.main import create_app
from app.models.audit import AuditRecord
from app.models.dispatch import Dispatch
from app.models.dispatch_publication import DispatchPublication
from app.models.task import DispatchTask
from app.security.permissions import Role
from app.security.ws_ticket import RedisWsTicketService
from app.services.dispatch_task_api_service import DispatchTaskApiService
from app.streams.redis_queue import RedisStreamQueue
from app.workers.dispatch_worker import DispatchWorker
from tests.unit.test_dispatch_service import _service
from tests.workers.test_worker_idempotency import _real_graph


def _app_with_events(role: Role = Role.ADMIN, *, real_tickets: bool = False):
    app = authorize_app(create_app(), role)
    temp, engine, factory = _service()
    redis = FakeRedis(decode_responses=False)
    broker = InMemoryTaskEventBroker()
    app.state.task_event_broker = broker
    app.state.dispatch_task_api_service = DispatchTaskApiService(
        factory,
        RedisStreamQueue(redis, "ws:tasks", "ws-workers", "ws-api"),
        event_broker=broker,
    )
    if real_tickets:
        app.state.ws_ticket_service = RedisWsTicketService(redis)
    return app, temp, engine, redis, broker


def _assign_task(service: DispatchTaskApiService, subject_id: str) -> None:
    with service._session_factory() as session:
        task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == "task-001"))
        task.assignee_subject_id = subject_id
        session.commit()


def _publish_task(service: DispatchTaskApiService) -> None:
    with service._session_factory() as session:
        task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == "task-001"))
        dispatch = Dispatch(
            dispatch_no="DSP-WS-PUBLISHED",
            order_id=task.order_id,
            task_id=task.id,
            original_route_id="route-original",
            target_route_id="route-published",
            status="COMPLETED",
        )
        session.add(dispatch)
        session.flush()
        session.add(
            DispatchPublication(
                task_id=task.id,
                dispatch_id=dispatch.id,
                status="PUBLISHED",
                route_id="route-published",
                route_instruction="按已发布路线行驶。",
                published_by_subject_id="test-supervisor",
                published_by_display_name="Test Supervisor",
                published_at=task.created_at,
            )
        )
        session.commit()


def _issue_task_ticket(client: TestClient) -> str:
    response = client.post(
        "/api/v1/ws-tickets",
        json={"target_type": "task", "target_id": "task-001"},
    )
    assert response.status_code == 201
    return response.json()["ticket"]


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


def test_assigned_employee_history_hides_unpublished_dispatch_details() -> None:
    app, temp, engine, redis, broker = _app_with_events(Role.EMPLOYEE, real_tickets=True)
    service = app.state.dispatch_task_api_service
    _assign_task(service, principal_for(Role.EMPLOYEE).subject_id)
    asyncio.run(
        broker.publish(
            TaskEvent.create(
                "task-001",
                TaskEventType.ROUTING_COMPLETED,
                "routing",
                "PROCESSING",
                data={
                    "progress": 70,
                    "routing_status": "ROUTED",
                    "recommended_route": "route-unpublished",
                    "decision_reason": "secret routing decision",
                    "candidate_routes": [{"route_id": "route-unpublished"}],
                    "original_path": {"edge_ids": ["E-ORIGINAL"]},
                    "recommended_path": {"edge_ids": ["E-UNPUBLISHED"]},
                    "blocked_edge_ids": ["E-BLOCKED"],
                    "distance_delta_km": "3.20",
                    "eta_delta_minutes": 4,
                    "visited_node_count": 8,
                    "algorithm": "DIJKSTRA_V1",
                    "road_network_version": 7,
                    "network_nodes": [{"node_id": "N-SECRET"}],
                    "network_edges": [{"edge_id": "E-UNPUBLISHED"}],
                },
            )
        )
    )
    try:
        with TestClient(app) as client:
            ticket = _issue_task_ticket(client)
            with client.websocket_connect(f"/api/v1/ws/tasks/task-001?ticket={ticket}") as socket:
                snapshot = socket.receive_json()
                replay = socket.receive_json()

        assert snapshot["event_type"] == "TASK_SNAPSHOT"
        assert replay["event_type"] == "ROUTING_COMPLETED"
        assert replay["task_id"] == "task-001"
        assert replay["node"] == "routing"
        assert replay["status"] == "PROCESSING"
        assert replay["data"] == {"progress": 70, "routing_status": "ROUTED"}
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_assigned_employee_live_events_become_visible_only_after_publication() -> None:
    app, temp, engine, redis, broker = _app_with_events(Role.EMPLOYEE, real_tickets=True)
    service = app.state.dispatch_task_api_service
    _assign_task(service, principal_for(Role.EMPLOYEE).subject_id)
    try:
        with TestClient(app) as client:
            ticket = _issue_task_ticket(client)
            with client.websocket_connect(f"/api/v1/ws/tasks/task-001?ticket={ticket}") as socket:
                assert socket.receive_json()["event_type"] == "TASK_SNAPSHOT"
                asyncio.run(
                    broker.publish(
                        TaskEvent.create(
                            "task-001",
                            TaskEventType.CAPACITY_COMPLETED,
                            "capacity",
                            "PROCESSING",
                            data={
                                "progress": 55,
                                "capacity_status": "REASSIGNED",
                                "vehicle_id": "V-001",
                                "candidate_vehicles": [{"vehicle_id": "V-005"}],
                                "selected_vehicle_id": "V-005",
                                "selected_driver_id": "D-003",
                                "vehicle_reassigned": True,
                                "pickup_route": {"edge_ids": ["E20"]},
                                "scoring_formula": "FLEET_SCORE_V1",
                            },
                        )
                    )
                )
                unpublished = socket.receive_json()
                _publish_task(service)
                asyncio.run(
                    broker.publish(
                        TaskEvent.create(
                            "task-001",
                            TaskEventType.DISPATCH_COMPLETED,
                            "dispatch",
                            "PROCESSING",
                            data={
                                "progress": 90,
                                "original_vehicle_id": "V-001",
                                "target_vehicle_id": "V-005",
                                "target_driver_id": "D-003",
                                "target_route_id": "route-published",
                                "status": "COMPLETED",
                            },
                        )
                    )
                )
                published = socket.receive_json()

        assert unpublished["event_type"] == "CAPACITY_COMPLETED"
        assert unpublished["data"] == {"progress": 55, "capacity_status": "REASSIGNED"}
        assert published["data"]["target_vehicle_id"] == "V-005"
        assert published["data"]["target_driver_id"] == "D-003"
        assert published["data"]["target_route_id"] == "route-published"
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_supervisor_history_sees_unpublished_dispatch_details() -> None:
    app, temp, engine, redis, broker = _app_with_events(Role.SUPERVISOR, real_tickets=True)
    asyncio.run(
        broker.publish(
            TaskEvent.create(
                "task-001",
                TaskEventType.ROUTING_COMPLETED,
                "routing",
                "PROCESSING",
                data={
                    "progress": 70,
                    "algorithm": "DIJKSTRA_V1",
                    "recommended_path": {"edge_ids": ["E-UNPUBLISHED"]},
                    "network_nodes": [{"node_id": "N-SECRET"}],
                    "network_edges": [{"edge_id": "E-UNPUBLISHED"}],
                },
            )
        )
    )
    try:
        with TestClient(app) as client:
            ticket = _issue_task_ticket(client)
            with client.websocket_connect(f"/api/v1/ws/tasks/task-001?ticket={ticket}") as socket:
                assert socket.receive_json()["event_type"] == "TASK_SNAPSHOT"
                replay = socket.receive_json()

        assert replay["data"]["algorithm"] == "DIJKSTRA_V1"
        assert replay["data"]["recommended_path"]["edge_ids"] == ["E-UNPUBLISHED"]
        assert replay["data"]["network_nodes"] == [{"node_id": "N-SECRET"}]
        assert replay["data"]["network_edges"] == [{"edge_id": "E-UNPUBLISHED"}]
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()
