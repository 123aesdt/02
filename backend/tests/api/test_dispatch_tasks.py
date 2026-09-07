import asyncio
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient
from security_support import authorize_app, principal_for

from app.main import create_app
from app.models.audit import AuditRecord
from app.models.demo_employee_account import DemoEmployeeAccount
from app.models.dispatch import Dispatch
from app.models.dispatch_publication import DispatchPublication
from app.models.task import DispatchTask
from app.security.dependencies import get_current_principal
from app.security.permissions import Role
from app.services.dispatch_task_api_service import DispatchTaskApiService
from app.streams.errors import QueueConnectionError
from app.streams.redis_queue import RedisStreamQueue
from tests.unit.test_dispatch_service import _service


def _status_app(task_status: str):
    app = authorize_app(create_app())
    temp, engine, factory = _service()
    redis = FakeRedis(decode_responses=False)
    app.state.dispatch_task_api_service = DispatchTaskApiService(
        factory,
        RedisStreamQueue(redis, "api:tasks", "api-workers", "api-test"),
    )
    with factory() as session:
        task = session.query(DispatchTask).filter_by(task_id="task-001").one()
        task.status = task_status
        session.commit()
    return app, temp, engine, redis


def _terminal_app(
    task_status: str,
    target_route_id: str = "national-102",
    audit_result: str = "APPROVED",
):
    app, temp, engine, redis = _status_app(task_status)
    service = app.state.dispatch_task_api_service
    with service._session_factory() as session:
        task = session.query(DispatchTask).filter_by(task_id="task-001").one()
        dispatch = Dispatch(
            dispatch_no="DSP-001",
            order_id=task.order_id,
            task_id=task.id,
            original_route_id="xinping-road",
            target_route_id=target_route_id,
            decision_reason="Safer route.",
            fallback_used=True,
            fallback_reason="Static route rule.",
            status="COMPLETED",
        )
        session.add(dispatch)
        session.flush()
        session.add(AuditRecord(task_id=task.id, dispatch_id=dispatch.id, result=audit_result, reason="Audit passed."))
        session.commit()
    return app, temp, engine, redis


def test_create_dispatch_task_returns_202():
    app = authorize_app(create_app())
    temp, engine, factory = _service()
    app.state.dispatch_task_api_service = DispatchTaskApiService(
        factory,
        RedisStreamQueue(FakeRedis(decode_responses=False), "api:tasks", "api-workers", "api-test"),
    )

    response = TestClient(app).post(
        "/api/v1/dispatch-tasks",
        json={
            "order_id": 1,
            "driver_id": "driver-li",
            "vehicle_id": "vehicle-001",
            "route_id": "xinping-road",
            "anomaly_type": "rain_slippery",
            "anomaly_description": "Road is slippery.",
            "idempotency_key": "api-idem-001",
        },
    )

    try:
        assert response.status_code == 202
        assert len(response.json()["task_id"]) <= 36
        with factory() as session:
            task = session.query(DispatchTask).filter_by(idempotency_key="api-idem-001").one()
            assert task.assignee_subject_id == "test-admin"
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.parametrize("role", [Role.DISPATCHER, Role.SUPERVISOR, Role.ADMIN])
def test_dispatch_staff_can_assign_a_new_dispatch_task_to_an_active_delivery_employee(role: Role):
    app = authorize_app(create_app(), role)
    temp, engine, factory = _service()
    redis = FakeRedis(decode_responses=False)
    app.state.dispatch_task_api_service = DispatchTaskApiService(
        factory,
        RedisStreamQueue(redis, "api:tasks", "api-workers", "api-test"),
    )
    with factory() as session:
        session.add(
            DemoEmployeeAccount(
                employee_id="CF-DEMO-001",
                display_name="张师傅",
                role="EMPLOYEE",
                is_active=True,
            )
        )
        session.commit()

    try:
        response = TestClient(app).post(
            "/api/v1/dispatch-tasks",
            json={
                "order_id": 1,
                "driver_id": "driver-li",
                "vehicle_id": "vehicle-001",
                "route_id": "xinping-road",
                "anomaly_type": "rain_slippery",
                "anomaly_description": "Road is slippery.",
                "idempotency_key": "api-idem-assignee",
                "assignee_employee_id": "CF-DEMO-001",
            },
        )

        assert response.status_code == 202
        with factory() as session:
            task = session.query(DispatchTask).filter_by(idempotency_key="api-idem-assignee").one()
        assert task.assignee_subject_id == "CF-DEMO-001"
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_delivery_employee_cannot_create_a_dispatch_task():
    app = authorize_app(create_app(), Role.EMPLOYEE)

    response = TestClient(app).post(
        "/api/v1/dispatch-tasks",
        json={
            "order_id": 1,
            "driver_id": "driver-li",
            "vehicle_id": "vehicle-001",
            "route_id": "xinping-road",
            "anomaly_type": "rain_slippery",
            "anomaly_description": "Road is slippery.",
            "idempotency_key": "api-employee-forbidden",
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "AUTHORIZATION_DENIED"


def test_delivery_employee_cannot_read_another_employees_task():
    app, temp, engine, redis = _status_app("COMPLETED")
    service = app.state.dispatch_task_api_service
    with service._session_factory() as session:
        task = session.query(DispatchTask).filter_by(task_id="task-001").one()
        task.assignee_subject_id = "CF-DEMO-006"
        session.commit()
    app.dependency_overrides[get_current_principal] = lambda: replace(principal_for(Role.EMPLOYEE), subject_id="CF-DEMO-001")
    try:
        status_response = TestClient(app).get("/api/v1/dispatch-tasks/task-001")
        result_response = TestClient(app).get("/api/v1/dispatch-tasks/task-001/result")

        assert status_response.status_code == 403
        assert result_response.status_code == 403
        assert status_response.json()["code"] == "TASK_ACCESS_FORBIDDEN"
        assert result_response.json()["code"] == "TASK_ACCESS_FORBIDDEN"
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_create_dispatch_task_publishes_stream_message():
    app = authorize_app(create_app())
    temp, engine, factory = _service()
    client = FakeRedis(decode_responses=False)
    app.state.dispatch_task_api_service = DispatchTaskApiService(factory, RedisStreamQueue(client, "api:tasks", "api-workers", "api-test"))
    try:
        response = TestClient(app).post(
            "/api/v1/dispatch-tasks",
            json={
                "order_id": 1,
                "driver_id": "driver-li",
                "vehicle_id": "vehicle-001",
                "route_id": "xinping-road",
                "anomaly_type": "rain_slippery",
                "anomaly_description": "Road is slippery.",
                "idempotency_key": "api-idem-stream",
            },
        )
        entries = asyncio.run(client.xrange("api:tasks"))
        assert response.status_code == 202
        assert len(entries) == 1
        assert b"api-idem-stream" in entries[0][1][b"data"]
    finally:
        asyncio.run(client.aclose())
        engine.dispose()
        temp.cleanup()


def test_create_dispatch_task_reuses_idempotency_key():
    app = authorize_app(create_app())
    temp, engine, factory = _service()
    client = FakeRedis(decode_responses=False)
    app.state.dispatch_task_api_service = DispatchTaskApiService(factory, RedisStreamQueue(client, "api:tasks", "api-workers", "api-test"))
    payload = {
        "order_id": 1,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-001",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "Road is slippery.",
        "idempotency_key": "api-idem-replay",
    }
    try:
        first = TestClient(app).post("/api/v1/dispatch-tasks", json=payload)
        replay = TestClient(app).post("/api/v1/dispatch-tasks", json=payload)
        assert first.status_code == replay.status_code == 202
        assert replay.json()["duplicate"] is True
        assert first.json()["task_id"] == replay.json()["task_id"]
        assert len(asyncio.run(client.xrange("api:tasks"))) == 1
    finally:
        asyncio.run(client.aclose())
        engine.dispose()
        temp.cleanup()


def test_create_dispatch_task_rejects_cross_employee_idempotency_replay():
    app = authorize_app(create_app())
    temp, engine, factory = _service()
    redis = FakeRedis(decode_responses=False)
    app.state.dispatch_task_api_service = DispatchTaskApiService(
        factory,
        RedisStreamQueue(redis, "api:tasks", "api-workers", "api-test"),
    )
    payload = {
        "order_id": 1,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-001",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "Road is slippery.",
        "idempotency_key": "api-idem-owner-boundary",
    }
    try:
        first = TestClient(app).post("/api/v1/dispatch-tasks", json=payload)
        another_principal = replace(principal_for(Role.ADMIN), subject_id="test-admin-other")
        app.dependency_overrides[get_current_principal] = lambda: another_principal

        replay = TestClient(app).post("/api/v1/dispatch-tasks", json=payload)

        assert first.status_code == 202
        assert replay.status_code == 409
        assert len(asyncio.run(redis.xrange("api:tasks"))) == 1
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_get_dispatch_task_not_found():
    app = authorize_app(create_app())
    temp, engine, factory = _service()
    client = FakeRedis(decode_responses=False)
    app.state.dispatch_task_api_service = DispatchTaskApiService(factory, RedisStreamQueue(client, "api:tasks", "api-workers", "api-test"))
    try:
        response = TestClient(app).get("/api/v1/dispatch-tasks/TASK-missing")
        assert response.status_code == 404
    finally:
        asyncio.run(client.aclose())
        engine.dispose()
        temp.cleanup()


class _FailingQueue:
    async def publish(self, _message):
        raise QueueConnectionError("redis://secret@internal:6379 refused")


def test_create_dispatch_task_conflicting_idempotency_key():
    app = authorize_app(create_app())
    temp, engine, factory = _service()
    client = FakeRedis(decode_responses=False)
    app.state.dispatch_task_api_service = DispatchTaskApiService(factory, RedisStreamQueue(client, "api:tasks", "api-workers", "api-test"))
    payload = {
        "order_id": 1,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-001",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "Road is slippery.",
        "idempotency_key": "idem-conflict",
    }
    try:
        assert TestClient(app).post("/api/v1/dispatch-tasks", json=payload).status_code == 202
        payload["order_id"] = 999
        response = TestClient(app).post("/api/v1/dispatch-tasks", json=payload)
        assert response.status_code == 409
        assert response.json() == {"code": "IDEMPOTENCY_CONFLICT", "message": "The idempotency key is already associated with another task."}
    finally:
        asyncio.run(client.aclose())
        engine.dispose()
        temp.cleanup()


def test_queue_publish_failure_does_not_leave_fake_pending_task():
    app = authorize_app(create_app())
    temp, engine, factory = _service()
    app.state.dispatch_task_api_service = DispatchTaskApiService(factory, _FailingQueue())
    payload = {
        "order_id": 1,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-001",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "Road is slippery.",
        "idempotency_key": "idem-failure",
    }
    try:
        response = TestClient(app).post("/api/v1/dispatch-tasks", json=payload)
        with factory() as session:
            task = session.query(DispatchTask).filter_by(idempotency_key="idem-failure").one()
        assert response.status_code == 503
        assert task.status == "SUBMISSION_FAILED"
    finally:
        engine.dispose()
        temp.cleanup()


def test_queue_error_does_not_leak_redis_details():
    app = authorize_app(create_app())
    temp, engine, factory = _service()
    app.state.dispatch_task_api_service = DispatchTaskApiService(factory, _FailingQueue())
    try:
        response = TestClient(app).post(
            "/api/v1/dispatch-tasks",
            json={
                "order_id": 1,
                "driver_id": "driver-li",
                "vehicle_id": "vehicle-001",
                "route_id": "xinping-road",
                "anomaly_type": "rain_slippery",
                "anomaly_description": "Road is slippery.",
                "idempotency_key": "idem-safe",
            },
        )
        assert response.json() == {"code": "QUEUE_UNAVAILABLE", "message": "Dispatch task could not be submitted. Please retry later."}
        assert "redis" not in response.text.lower()
    finally:
        engine.dispose()
        temp.cleanup()


def test_submission_failure_reuses_task_id_and_publishes_once_on_retry():
    app = authorize_app(create_app())
    temp, engine, factory = _service()
    redis = FakeRedis(decode_responses=False)
    service = DispatchTaskApiService(factory, _FailingQueue())
    app.state.dispatch_task_api_service = service
    payload = {
        "order_id": 1,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-001",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "Road is slippery.",
        "idempotency_key": "idem-recover",
    }
    try:
        first = TestClient(app).post("/api/v1/dispatch-tasks", json=payload)
        service._queue = RedisStreamQueue(redis, "api:tasks", "api-workers", "api-test")
        retry = TestClient(app).post("/api/v1/dispatch-tasks", json=payload)

        with factory() as session:
            task = session.query(DispatchTask).filter_by(idempotency_key="idem-recover").one()
        assert first.status_code == 503
        assert retry.status_code == 202
        assert retry.json()["task_id"] == task.task_id
        assert task.status == "PENDING"
        assert len(asyncio.run(redis.xrange("api:tasks"))) == 1
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_get_dispatch_task_status_pending():
    app, temp, engine, redis = _status_app("PENDING")
    try:
        response = TestClient(app).get("/api/v1/dispatch-tasks/task-001")
        assert response.status_code == 200
        assert response.json()["status"] == "PENDING"
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_get_dispatch_task_status_review_required():
    app, temp, engine, redis = _status_app("REVIEW_REQUIRED")
    try:
        response = TestClient(app).get("/api/v1/dispatch-tasks/task-001")
        assert response.status_code == 200
        assert response.json()["status"] == "REVIEW_REQUIRED"
        assert response.json()["ready"] is True
        assert response.json()["requires_manual_review"] is True
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_get_dispatch_result_not_ready():
    app, temp, engine, redis = _status_app("PROCESSING")
    try:
        response = TestClient(app).get("/api/v1/dispatch-tasks/task-001/result")
        assert response.status_code == 202
        assert response.json()["ready"] is False
        assert response.json()["status"] == "PROCESSING"
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_get_dispatch_task_status_processing():
    app, temp, engine, redis = _status_app("PROCESSING")
    try:
        response = TestClient(app).get("/api/v1/dispatch-tasks/task-001")
        assert response.status_code == 200
        assert response.json()["status"] == "PROCESSING"
        assert response.json()["ready"] is False
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_get_dispatch_task_status_completed():
    app, temp, engine, redis = _status_app("COMPLETED")
    try:
        response = TestClient(app).get("/api/v1/dispatch-tasks/task-001")
        assert response.status_code == 200
        assert response.json()["status"] == "COMPLETED"
        assert response.json()["ready"] is True
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_get_dispatch_task_status_submission_failed():
    app, temp, engine, redis = _status_app("SUBMISSION_FAILED")
    try:
        response = TestClient(app).get("/api/v1/dispatch-tasks/task-001")
        assert response.status_code == 200
        assert response.json()["status"] == "SUBMISSION_FAILED"
        assert response.json()["ready"] is False
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_get_dispatch_result_completed():
    app, temp, engine, redis = _terminal_app("COMPLETED")
    try:
        response = TestClient(app).get("/api/v1/dispatch-tasks/task-001/result")
        assert response.status_code == 200
        assert response.json()["ready"] is True
        assert response.json()["dispatch"]["target_route_id"] == "national-102"
        assert response.json()["audit"]["result"] == "APPROVED"
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_get_dispatch_result_uses_database_facts():
    app, temp, engine, redis = _terminal_app("COMPLETED", "county-308")
    try:
        response = TestClient(app).get("/api/v1/dispatch-tasks/task-001/result")
        assert response.status_code == 200
        assert response.json()["dispatch"]["target_route_id"] == "county-308"
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_get_dispatch_result_marks_rerouted_dispatch_as_executed():
    app, temp, engine, redis = _terminal_app("COMPLETED")
    try:
        service = app.state.dispatch_task_api_service
        with service._session_factory() as session:
            session.query(Dispatch).filter_by(dispatch_no="DSP-001").update({"status": "REROUTED"})
            session.commit()
        response = TestClient(app).get("/api/v1/dispatch-tasks/task-001/result")
        assert response.status_code == 200
        assert response.json()["dispatch"]["executed"] is True
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_get_dispatch_result_review_required():
    app, temp, engine, redis = _terminal_app("REVIEW_REQUIRED", audit_result="REVIEW_REQUIRED")
    try:
        response = TestClient(app).get("/api/v1/dispatch-tasks/task-001/result")
        assert response.status_code == 200
        assert response.json()["ready"] is True
        assert response.json()["status"] == "REVIEW_REQUIRED"
        assert response.json()["audit"]["result"] == "REVIEW_REQUIRED"
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_get_dispatch_result_not_found():
    app, temp, engine, redis = _status_app("PENDING")
    try:
        response = TestClient(app).get("/api/v1/dispatch-tasks/task-missing/result")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "TASK_NOT_FOUND"
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_dispatcher_cannot_read_an_unpublished_route_from_task_result() -> None:
    app, temp, engine, redis = _terminal_app("COMPLETED")
    app.dependency_overrides[get_current_principal] = lambda: principal_for(Role.DISPATCHER)
    try:
        response = TestClient(app).get("/api/v1/dispatch-tasks/task-001/result")

        assert response.status_code == 200
        assert response.json()["dispatch"]["target_route_id"] is None
        assert response.json()["dispatch"]["decision_reason"] is None
        assert response.json()["publication"] == {
            "status": "PENDING",
            "route_id": None,
            "route_instruction": None,
            "published_at": None,
            "published_by": None,
            "recipient_employee_id": None,
            "recipient_display_name": None,
        }
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_dispatcher_reads_the_route_after_local_publication() -> None:
    app, temp, engine, redis = _terminal_app("COMPLETED")
    service = app.state.dispatch_task_api_service
    published_at = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    with service._session_factory() as session:
        task = session.query(DispatchTask).filter_by(task_id="task-001").one()
        dispatch = session.query(Dispatch).filter_by(task_id=task.id).one()
        session.add(
            DispatchPublication(
                task_id=task.id,
                dispatch_id=dispatch.id,
                status="PUBLISHED",
                route_id="national-102",
                route_instruction="从 A 出发，按 national-102 行驶，前往 B。途中注意现场路况并服从安全调度。",
                published_by_subject_id="test-supervisor",
                published_by_display_name="Test Supervisor",
                published_at=published_at,
            )
        )
        session.commit()
    app.dependency_overrides[get_current_principal] = lambda: principal_for(Role.DISPATCHER)
    try:
        response = TestClient(app).get("/api/v1/dispatch-tasks/task-001/result")

        assert response.status_code == 200
        assert response.json()["dispatch"]["target_route_id"] == "national-102"
        assert response.json()["publication"] == {
            "status": "PUBLISHED",
            "route_id": "national-102",
            "route_instruction": "从 A 出发，按 national-102 行驶，前往 B。途中注意现场路况并服从安全调度。",
            "published_at": "2026-08-30T12:00:00Z",
            "published_by": "Test Supervisor",
            "recipient_employee_id": None,
            "recipient_display_name": None,
        }
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


class _PublicationService:
    def __init__(self) -> None:
        self.calls = []

    def publish(self, task_id, principal):
        self.calls.append((task_id, principal))
        return {
            "task_id": task_id,
            "dispatch_id": 42,
            "status": "PUBLISHED",
            "route_id": "national-102",
            "route_instruction": "从青云镇出发，按 national-102 行驶，前往临港镇。",
            "published_at": "2026-08-30T12:00:00Z",
            "published_by": principal.display_name,
            "recipient_employee_id": "CF-DEMO-001",
            "recipient_display_name": "张调度",
            "duplicate": False,
        }


@pytest.mark.parametrize("role", [Role.SUPERVISOR, Role.ADMIN])
def test_supervisor_and_admin_can_publish_an_approved_dispatch(role: Role) -> None:
    from fastapi import FastAPI

    from app.api.v1.dispatch_tasks import router

    service = _PublicationService()
    app = authorize_app(FastAPI(), role)
    app.state.dispatch_publication_service = service
    app.include_router(router)

    response = TestClient(app).post("/api/v1/dispatch-tasks/TASK-approved-1/publish")

    assert response.status_code == 200
    assert response.json() == {
        "task_id": "TASK-approved-1",
        "dispatch_id": 42,
        "status": "PUBLISHED",
        "route_id": "national-102",
        "route_instruction": "从青云镇出发，按 national-102 行驶，前往临港镇。",
        "published_at": "2026-08-30T12:00:00Z",
        "published_by": f"Test {role.value.title()}",
        "recipient_employee_id": "CF-DEMO-001",
        "recipient_display_name": "张调度",
        "duplicate": False,
    }
    assert service.calls[0][0] == "TASK-approved-1"
    assert service.calls[0][1].subject_id == f"test-{role.value.lower()}"


def test_dispatcher_cannot_publish_a_dispatch() -> None:
    from fastapi import FastAPI

    from app.api.v1.dispatch_tasks import router

    service = _PublicationService()
    app = authorize_app(FastAPI(), Role.DISPATCHER)
    app.state.dispatch_publication_service = service
    app.include_router(router)

    response = TestClient(app).post("/api/v1/dispatch-tasks/TASK-approved-1/publish")

    assert response.status_code == 403
    assert response.json()["code"] == "AUTHORIZATION_DENIED"
    assert service.calls == []


def _persist_task_7_evidence(service: DispatchTaskApiService) -> None:
    from app.models.dispatch_evidence import DispatchEvidence

    with service._session_factory() as session:
        task = session.query(DispatchTask).filter_by(task_id="task-001").one()
        dispatch = session.query(Dispatch).filter_by(task_id=task.id).one()
        dispatch.original_vehicle_id = "V-001"
        dispatch.target_vehicle_id = "V-005"
        dispatch.target_driver_id = "D-003"
        dispatch.transfer_node_id = "N04"
        session.add_all(
            [
                DispatchEvidence(
                    dispatch_id=dispatch.id,
                    evidence_type="FLEET_ALLOCATION",
                    algorithm_version="FLEET_SCORE_V1",
                    payload_json={
                        "original_vehicle_id": "V-001",
                        "target_vehicle_id": "V-005",
                        "target_driver_id": "D-003",
                        "vehicle_reassigned": True,
                        "pickup_route": {
                            "objective": "FASTEST",
                            "node_ids": ["N15", "N04"],
                            "edge_ids": ["E20"],
                            "distance_km": "2.80",
                            "estimated_minutes": 6,
                            "risk_cost": "0",
                            "visited_node_count": 2,
                        },
                        "candidates": [
                            {
                                "vehicle_id": "V-005",
                                "driver_id": "D-003",
                                "vehicle_status": "AVAILABLE",
                                "driver_status": "ON_DUTY",
                                "remaining_capacity_kg": "900.00",
                                "gross_weight_tons": "2.40",
                                "cargo_capability": "COLD_CHAIN",
                                "pickup_distance_km": "2.80",
                                "pickup_eta_minutes": 6,
                                "score": "93.4",
                                "score_components": {
                                    "eta_penalty": "9.0",
                                    "distance_penalty": "5.60",
                                    "load_penalty": "2.0",
                                    "road_risk_penalty": "0",
                                    "same_station_bonus": "0",
                                    "cargo_exact_match_bonus": "10",
                                },
                                "scoring_formula": "FLEET_SCORE_V1",
                                "eligible": True,
                                "exclusion_reasons": [],
                            }
                        ],
                    },
                ),
                DispatchEvidence(
                    dispatch_id=dispatch.id,
                    evidence_type="ROUTE_CALCULATION",
                    algorithm_version="DIJKSTRA_V1",
                    road_network_version=7,
                    payload_json={
                        "original_path": {
                            "objective": "FASTEST",
                            "node_ids": ["N01", "N02", "N03", "N04", "N05", "N06"],
                            "edge_ids": ["E01", "E02", "E03", "E04", "E05"],
                            "distance_km": "10.00",
                            "estimated_minutes": 20,
                            "risk_cost": "2",
                            "visited_node_count": 6,
                        },
                        "recommended_path": {
                            "objective": "FASTEST",
                            "node_ids": ["N01", "N02", "N07", "N08", "N09", "N06"],
                            "edge_ids": ["E01", "E06", "E07", "E08", "E09"],
                            "distance_km": "13.20",
                            "estimated_minutes": 24,
                            "risk_cost": "0",
                            "visited_node_count": 8,
                            "scoring_formula": "ROUTE_SCORE_V1",
                        },
                        "candidate_routes": [
                            {
                                "route_id": "RTE-RECOMMENDED",
                                "route_name": "最快路线",
                                "objective": "FASTEST",
                                "node_ids": ["N01", "N02", "N07", "N08", "N09", "N06"],
                                "edge_ids": ["E01", "E06", "E07", "E08", "E09"],
                                "distance_km": "13.20",
                                "estimated_minutes": 24,
                                "risk_level": "LOW",
                                "risk_cost": "0",
                                "visited_node_count": 8,
                                "available": True,
                                "reason": None,
                                "score": "100.00",
                                "scoring_formula": "ROUTE_SCORE_V1",
                            }
                        ],
                        "blocked_edge_ids": ["E04"],
                        "distance_delta_km": "3.20",
                        "eta_delta_minutes": 4,
                        "routing_status": "ROUTED",
                        "visited_node_count": 8,
                        "network_nodes": [
                            {"node_id": "N01", "name": "中心仓", "x_km": "0.00", "y_km": "0.00", "node_type": "STATION"},
                            {"node_id": "N06", "name": "城东站", "x_km": "10.00", "y_km": "2.00", "node_type": "STATION"},
                        ],
                        "network_edges": [
                            {
                                "edge_id": "E04",
                                "name": "新平路东河桥段",
                                "from_node_id": "N04",
                                "to_node_id": "N05",
                                "distance_km": "2.50",
                                "base_minutes": 5,
                                "road_level": "COUNTY",
                                "risk_level": "HIGH",
                                "status": "BLOCKED",
                                "congestion_factor": "1.00",
                                "weight_limit_tons": "6.00",
                                "bidirectional": True,
                                "version": 2,
                            }
                        ],
                    },
                ),
            ]
        )
        session.commit()


def test_supervisor_reads_persisted_fleet_and_route_evidence_snapshot() -> None:
    app, temp, engine, redis = _terminal_app("COMPLETED")
    service = app.state.dispatch_task_api_service
    _persist_task_7_evidence(service)
    app.dependency_overrides[get_current_principal] = lambda: principal_for(Role.SUPERVISOR)
    try:
        response = TestClient(app).get("/api/v1/dispatch-tasks/task-001/result")
        body = response.json()

        assert response.status_code == 200
        assert body["vehicle_allocation"]["target_vehicle_id"] == "V-005"
        assert body["vehicle_allocation"]["target_driver_id"] == "D-003"
        assert body["vehicle_allocation"]["pickup_route"]["edge_ids"] == ["E20"]
        assert body["vehicle_allocation"]["scoring_formula"] == "FLEET_SCORE_V1"
        assert body["route_plan"]["distance_delta_km"] == "3.20"
        assert body["route_plan"]["algorithm"] == "DIJKSTRA_V1"
        assert body["route_plan"]["road_network_version"] == 7
        assert "E04" not in body["route_plan"]["recommended_path"]["edge_ids"]
        assert body["route_plan"]["network_nodes"][0]["x_km"] == "0.00"
        assert body["route_plan"]["network_edges"][0]["status"] == "BLOCKED"
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_delivery_employee_cannot_read_unpublished_fleet_or_route_evidence() -> None:
    app, temp, engine, redis = _terminal_app("COMPLETED")
    service = app.state.dispatch_task_api_service
    _persist_task_7_evidence(service)
    employee = principal_for(Role.EMPLOYEE)
    with service._session_factory() as session:
        task = session.query(DispatchTask).filter_by(task_id="task-001").one()
        task.assignee_subject_id = employee.subject_id
        session.commit()
    app.dependency_overrides[get_current_principal] = lambda: employee
    try:
        response = TestClient(app).get("/api/v1/dispatch-tasks/task-001/result")
        body = response.json()

        assert response.status_code == 200
        assert body["dispatch"]["target_route_id"] is None
        assert body["vehicle_allocation"] is None
        assert body["route_plan"] is None
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_result_rejects_malformed_or_duplicate_evidence_without_leaking_internal_fields() -> None:
    from app.models.dispatch_evidence import DispatchEvidence

    app, temp, engine, redis = _terminal_app("COMPLETED")
    service = app.state.dispatch_task_api_service
    _persist_task_7_evidence(service)
    with service._session_factory() as session:
        route = session.query(DispatchEvidence).filter_by(evidence_type="ROUTE_CALCULATION").one()
        malformed = dict(route.payload_json)
        malformed["authorization"] = "Bearer must-not-leak"
        malformed["network_nodes"] = [{"node_id": "N01", "name": "中心仓", "x_km": 0, "y_km": "0.00", "node_type": "STATION"}]
        route.payload_json = malformed
        session.commit()
    try:
        malformed_response = TestClient(app).get("/api/v1/dispatch-tasks/task-001/result")
        malformed_body = malformed_response.json()

        assert malformed_response.status_code == 200
        assert malformed_body["vehicle_allocation"] is None
        assert malformed_body["route_plan"] is None
        assert "must-not-leak" not in malformed_response.text

        with service._session_factory() as session:
            dispatch = session.query(Dispatch).filter_by(dispatch_no="DSP-001").one()
            session.add(
                DispatchEvidence(
                    dispatch_id=dispatch.id,
                    evidence_type="FLEET_ALLOCATION",
                    algorithm_version="FLEET_SCORE_V1",
                    payload_json={},
                )
            )
            session.commit()
        duplicate_response = TestClient(app).get("/api/v1/dispatch-tasks/task-001/result")

        assert duplicate_response.status_code == 200
        assert duplicate_response.json()["vehicle_allocation"] is None
        assert duplicate_response.json()["route_plan"] is None
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


def test_result_rejects_selected_candidate_identity_tampering() -> None:
    from app.models.dispatch_evidence import DispatchEvidence

    app, temp, engine, redis = _terminal_app("COMPLETED")
    service = app.state.dispatch_task_api_service
    _persist_task_7_evidence(service)
    with service._session_factory() as session:
        fleet = session.query(DispatchEvidence).filter_by(evidence_type="FLEET_ALLOCATION").one()
        payload = dict(fleet.payload_json)
        payload["selected_candidate"] = {
            "vehicle_id": "V-TAMPERED",
            "driver_id": "D-TAMPERED",
            "vehicle_status": "AVAILABLE",
        }
        fleet.payload_json = payload
        session.commit()
    try:
        response = TestClient(app).get("/api/v1/dispatch-tasks/task-001/result")

        assert response.status_code == 200
        assert response.json()["vehicle_allocation"] is None
        assert response.json()["route_plan"] is None
        assert "TAMPERED" not in response.text
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()


@pytest.mark.parametrize(
    "corruption",
    [
        "empty_recommended_path",
        "recommended_path_missing_distance",
        "candidate_route_missing_distance",
        "recommended_path_wrong_eta_type",
    ],
)
def test_result_rejects_incomplete_or_wrong_typed_path_evidence(corruption: str) -> None:
    from app.models.dispatch_evidence import DispatchEvidence

    app, temp, engine, redis = _terminal_app("COMPLETED")
    service = app.state.dispatch_task_api_service
    _persist_task_7_evidence(service)
    with service._session_factory() as session:
        route = session.query(DispatchEvidence).filter_by(evidence_type="ROUTE_CALCULATION").one()
        payload = dict(route.payload_json)
        if corruption == "empty_recommended_path":
            payload["recommended_path"] = {}
        elif corruption == "recommended_path_missing_distance":
            recommended_path = dict(payload["recommended_path"])
            recommended_path.pop("distance_km")
            payload["recommended_path"] = recommended_path
        elif corruption == "candidate_route_missing_distance":
            candidate = dict(payload["candidate_routes"][0])
            candidate.pop("distance_km")
            payload["candidate_routes"] = [candidate]
        else:
            recommended_path = dict(payload["recommended_path"])
            recommended_path["estimated_minutes"] = "24"
            payload["recommended_path"] = recommended_path
        route.payload_json = payload
        session.commit()
    try:
        response = TestClient(app).get("/api/v1/dispatch-tasks/task-001/result")

        assert response.status_code == 200
        assert response.json()["vehicle_allocation"] is None
        assert response.json()["route_plan"] is None
    finally:
        asyncio.run(redis.aclose())
        engine.dispose()
        temp.cleanup()
