import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.audit import AuditRecord
from app.models.dispatch import Dispatch
from app.models.order import Order
from app.models.task import DispatchTask
from app.security.models import AuthenticatedPrincipal, AuthMethod
from app.security.permissions import ROLE_PERMISSION_MATRIX, Role

DECIDED_AT = datetime(2026, 8, 30, 9, 45, tzinfo=UTC)


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        subject_id="demo-supervisor",
        display_name="王主管",
        roles=frozenset({Role.SUPERVISOR}),
        permissions=ROLE_PERMISSION_MATRIX[Role.SUPERVISOR],
        auth_method=AuthMethod.DEVELOPMENT_JWT,
        issued_at=DECIDED_AT - timedelta(minutes=5),
        expires_at=DECIDED_AT + timedelta(hours=1),
        jti="review-session",
    )


def _seed_review(factory, *, task_status: str = "REVIEW_REQUIRED", with_dispatch: bool = True) -> None:
    with factory() as session:
        order = Order(
            id=101,
            order_no="DEMO-ORDER-101",
            status="DELAYED",
            origin="青云镇",
            destination="县城分拨中心",
        )
        task = DispatchTask(
            id=201,
            task_id="DEMO-TASK-101",
            order_id=101,
            status=task_status,
            idempotency_key="demo-review-101",
        )
        session.add_all([order, task])
        if with_dispatch:
            dispatch = Dispatch(
                id=301,
                dispatch_no="DEMO-DISPATCH-101",
                order_id=101,
                task_id=201,
                original_route_id="青云乡道",
                target_route_id="国道-102",
                decision_reason="道路积水，建议安全绕行",
                status="PENDING_REVIEW",
            )
            session.add(dispatch)
            session.add(
                AuditRecord(
                    id=401,
                    task_id=201,
                    dispatch_id=301,
                    result="REVIEW_REQUIRED",
                    reason="高风险异常需要人工复核",
                    evidence_json="{}",
                )
            )
        session.commit()


def test_approve_persists_task_dispatch_and_reviewer_audit_atomically(sqlite_factory) -> None:
    from app.reviews.models import ReviewDecision
    from app.reviews.service import ReviewDecisionService

    _seed_review(sqlite_factory)

    result = ReviewDecisionService(sqlite_factory, clock=lambda: DECIDED_AT).decide(
        "DEMO-TASK-101",
        ReviewDecision.APPROVE,
        "同意按安全绕行方案执行",
        _principal(),
    )

    assert result.task_id == "DEMO-TASK-101"
    assert result.decision is ReviewDecision.APPROVE
    assert result.status == "APPROVED"
    assert result.reviewer == "王主管"
    assert result.dispatch_version == 2
    assert result.decided_at == DECIDED_AT
    with sqlite_factory() as session:
        task = session.scalar(select(DispatchTask).where(DispatchTask.id == 201))
        dispatch = session.scalar(select(Dispatch).where(Dispatch.id == 301))
        audits = session.scalars(select(AuditRecord).where(AuditRecord.task_id == 201).order_by(AuditRecord.id)).all()
    assert task is not None and task.status == "APPROVED"
    assert task.completed_at is not None and task.completed_at.replace(tzinfo=UTC) == DECIDED_AT
    assert dispatch is not None and dispatch.status == "APPROVED" and dispatch.version == 2
    assert [(item.result, item.reason) for item in audits] == [
        ("REVIEW_REQUIRED", "高风险异常需要人工复核"),
        ("APPROVED", "同意按安全绕行方案执行"),
    ]
    assert json.loads(audits[-1].evidence_json) == {
        "decision": "APPROVE",
        "decided_at": "2026-08-30T09:45:00+00:00",
        "reviewer_display_name": "王主管",
        "reviewer_subject_id": "demo-supervisor",
    }


def test_reject_requires_reason_and_persists_rejected_terminal_state(sqlite_factory) -> None:
    from app.reviews.models import ReviewDecision
    from app.reviews.service import ReviewDecisionService, ReviewReasonRequired

    _seed_review(sqlite_factory)
    service = ReviewDecisionService(sqlite_factory, clock=lambda: DECIDED_AT)

    with pytest.raises(ReviewReasonRequired):
        service.decide("DEMO-TASK-101", ReviewDecision.REJECT, " ", _principal())

    result = service.decide(
        "DEMO-TASK-101",
        ReviewDecision.REJECT,
        "车辆状态信息不完整，需要重新评估",
        _principal(),
    )

    assert result.status == "REJECTED"
    with sqlite_factory() as session:
        task = session.scalar(select(DispatchTask).where(DispatchTask.id == 201))
        dispatch = session.scalar(select(Dispatch).where(Dispatch.id == 301))
        latest_audit = session.scalar(select(AuditRecord).where(AuditRecord.task_id == 201).order_by(AuditRecord.id.desc()))
    assert task is not None and task.status == "REJECTED"
    assert dispatch is not None and dispatch.status == "REJECTED"
    assert latest_audit is not None and (latest_audit.result, latest_audit.reason) == (
        "REJECTED",
        "车辆状态信息不完整，需要重新评估",
    )


def test_approve_without_note_uses_stable_human_review_reason(sqlite_factory) -> None:
    from app.reviews.models import ReviewDecision
    from app.reviews.service import ReviewDecisionService

    _seed_review(sqlite_factory)

    ReviewDecisionService(sqlite_factory, clock=lambda: DECIDED_AT).decide(
        "DEMO-TASK-101", ReviewDecision.APPROVE, None, _principal()
    )

    with sqlite_factory() as session:
        latest_audit = session.scalar(select(AuditRecord).where(AuditRecord.task_id == 201).order_by(AuditRecord.id.desc()))
    assert latest_audit is not None and latest_audit.reason == "人工复核已批准。"


def test_missing_review_task_is_not_treated_as_an_empty_queue(sqlite_factory) -> None:
    from app.reviews.models import ReviewDecision
    from app.reviews.service import ReviewDecisionService, ReviewNotFound

    with pytest.raises(ReviewNotFound):
        ReviewDecisionService(sqlite_factory, clock=lambda: DECIDED_AT).decide(
            "MISSING-TASK", ReviewDecision.APPROVE, None, _principal()
        )


def test_already_decided_task_cannot_be_decided_again(sqlite_factory) -> None:
    from app.reviews.models import ReviewDecision
    from app.reviews.service import ReviewAlreadyDecided, ReviewDecisionService

    _seed_review(sqlite_factory, task_status="APPROVED")

    with pytest.raises(ReviewAlreadyDecided):
        ReviewDecisionService(sqlite_factory, clock=lambda: DECIDED_AT).decide(
            "DEMO-TASK-101", ReviewDecision.REJECT, "重新拒绝", _principal()
        )


def test_review_without_a_persisted_dispatch_is_rejected_without_partial_state(sqlite_factory) -> None:
    from app.reviews.models import ReviewDecision
    from app.reviews.service import ReviewDecisionService, ReviewDispatchMissing

    _seed_review(sqlite_factory, with_dispatch=False)

    with pytest.raises(ReviewDispatchMissing):
        ReviewDecisionService(sqlite_factory, clock=lambda: DECIDED_AT).decide(
            "DEMO-TASK-101", ReviewDecision.APPROVE, None, _principal()
        )

    with sqlite_factory() as session:
        task = session.scalar(select(DispatchTask).where(DispatchTask.id == 201))
        audits = session.scalars(select(AuditRecord).where(AuditRecord.task_id == 201)).all()
    assert task is not None and task.status == "REVIEW_REQUIRED" and task.completed_at is None
    assert audits == []
