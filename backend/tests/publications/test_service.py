from datetime import UTC, datetime
from importlib import import_module

import pytest
from security_support import principal_for
from sqlalchemy import func, select

from app.models.audit import AuditRecord
from app.models.demo_employee_account import DemoEmployeeAccount
from app.models.dispatch import Dispatch
from app.models.task import DispatchTask
from app.security.permissions import Role
from tests.unit.test_dispatch_service import _service

PUBLISHED_AT = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def publication_module():
    return import_module("app.publications.service")


def approved_fixture():
    temp, engine, factory = _service()
    with factory() as session:
        task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == "task-001"))
        task.status = "COMPLETED"
        task.assignee_subject_id = "CF-DEMO-001"
        session.add(
            DemoEmployeeAccount(
                employee_id="CF-DEMO-001",
                display_name="张调度",
                role="DISPATCHER",
                is_active=True,
            )
        )
        dispatch = Dispatch(
            dispatch_no="DSP-PUBLISH-001",
            order_id=task.order_id,
            task_id=task.id,
            original_route_id="xinping-road",
            target_route_id="national-102",
            decision_reason="更加安全",
            status="REROUTED",
        )
        session.add(dispatch)
        session.flush()
        session.add(
            AuditRecord(
                task_id=task.id,
                dispatch_id=dispatch.id,
                result="APPROVED",
                reason="审核通过",
            )
        )
        session.commit()
    return temp, engine, factory


def test_publish_persists_the_approved_route_and_authenticated_operator() -> None:
    module = publication_module()
    temp, engine, factory = approved_fixture()
    try:
        service = module.DispatchPublicationService(factory, clock=lambda: PUBLISHED_AT)

        result = service.publish("task-001", principal_for(Role.SUPERVISOR))

        publication_model = import_module("app.models.dispatch_publication").DispatchPublication
        with factory() as session:
            publication = session.scalar(select(publication_model))
        assert result == {
            "task_id": "task-001",
            "dispatch_id": 1,
            "status": "PUBLISHED",
            "route_id": "national-102",
            "route_instruction": "从 A 出发，按 national-102 行驶，前往 B。途中注意现场路况并服从安全调度。",
            "published_at": PUBLISHED_AT,
            "published_by": "Test Supervisor",
            "recipient_employee_id": "CF-DEMO-001",
            "recipient_display_name": "张调度",
            "duplicate": False,
        }
        assert publication.published_by_subject_id == "test-supervisor"
        assert publication.route_id == "national-102"
    finally:
        engine.dispose()
        temp.cleanup()


def test_automatic_publish_records_the_system_actor_and_is_idempotent() -> None:
    module = publication_module()
    temp, engine, factory = approved_fixture()
    try:
        service = module.DispatchPublicationService(factory, clock=lambda: PUBLISHED_AT)

        first = service.publish_automatically("task-001")
        second = service.publish_automatically("task-001")

        publication_model = import_module("app.models.dispatch_publication").DispatchPublication
        with factory() as session:
            publication = session.scalar(select(publication_model))
        assert first["published_by"] == "CountyFlow AI 自动发布"
        assert first["duplicate"] is False
        assert second["duplicate"] is True
        assert publication.published_by_subject_id == "countyflow-ai"
        assert publication.published_by_display_name == "CountyFlow AI 自动发布"
    finally:
        engine.dispose()
        temp.cleanup()


def test_publish_is_idempotent_and_does_not_duplicate_the_local_audit_record() -> None:
    module = publication_module()
    temp, engine, factory = approved_fixture()
    try:
        service = module.DispatchPublicationService(factory, clock=lambda: PUBLISHED_AT)
        principal = principal_for(Role.ADMIN)

        first = service.publish("task-001", principal)
        second = service.publish("task-001", principal)

        publication_model = import_module("app.models.dispatch_publication").DispatchPublication
        with factory() as session:
            count = session.scalar(select(func.count()).select_from(publication_model))
        assert first["duplicate"] is False
        assert second["duplicate"] is True
        assert second["published_at"] == PUBLISHED_AT
        assert count == 1
    finally:
        engine.dispose()
        temp.cleanup()


def test_publish_rejects_a_task_without_an_approved_audit() -> None:
    module = publication_module()
    temp, engine, factory = _service()
    try:
        with factory() as session:
            task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == "task-001"))
            task.status = "REVIEW_REQUIRED"
            dispatch = Dispatch(
                dispatch_no="DSP-REVIEW-001",
                order_id=task.order_id,
                task_id=task.id,
                original_route_id="xinping-road",
                target_route_id="national-102",
                status="PENDING_REVIEW",
            )
            session.add(dispatch)
            session.flush()
            session.add(
                AuditRecord(
                    task_id=task.id,
                    dispatch_id=dispatch.id,
                    result="REVIEW_REQUIRED",
                    reason="需要人工复核",
                )
            )
            session.commit()

        service = module.DispatchPublicationService(factory, clock=lambda: PUBLISHED_AT)
        with pytest.raises(module.PublicationNotApproved):
            service.publish("task-001", principal_for(Role.SUPERVISOR))
    finally:
        engine.dispose()
        temp.cleanup()
