from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from security_support import authorize_app

from app.reviews.models import ReviewDecision, ReviewDecisionResult
from app.reviews.service import (
    ReviewAlreadyDecided,
    ReviewDispatchMissing,
    ReviewNotFound,
    ReviewVersionConflict,
)
from app.security.permissions import Role

DECIDED_AT = datetime(2026, 8, 30, 10, 15, tzinfo=UTC)


class ReviewService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls = []

    def decide(self, task_id, decision, reason, principal):
        self.calls.append((task_id, decision, reason, principal))
        if self.error is not None:
            raise self.error
        return ReviewDecisionResult(
            task_id=task_id,
            decision=decision,
            status="APPROVED" if decision is ReviewDecision.APPROVE else "REJECTED",
            reviewer=principal.display_name,
            decided_at=DECIDED_AT,
            dispatch_version=2,
        )


def application(service: ReviewService, role: Role = Role.ADMIN) -> FastAPI:
    from app.api.v1.review_decisions import router

    app = authorize_app(FastAPI(), role)
    app.state.review_decision_service = service
    app.include_router(router)
    return app


@pytest.mark.parametrize("role", [Role.SUPERVISOR, Role.ADMIN])
def test_supervisor_and_admin_can_approve_from_the_authenticated_identity(role: Role) -> None:
    service = ReviewService()

    response = TestClient(application(service, role)).post(
        "/api/v1/reviews/DEMO-TASK-101/decision",
        json={"decision": "APPROVE", "reason": "同意执行"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "task_id": "DEMO-TASK-101",
        "decision": "APPROVE",
        "status": "APPROVED",
        "reviewer": f"Test {role.value.title()}",
        "decided_at": "2026-08-30T10:15:00Z",
        "dispatch_version": 2,
    }
    task_id, decision, reason, principal = service.calls[0]
    assert (task_id, decision, reason) == ("DEMO-TASK-101", ReviewDecision.APPROVE, "同意执行")
    assert principal.subject_id == f"test-{role.value.lower()}"


def test_dispatcher_cannot_reach_the_review_decision_service() -> None:
    service = ReviewService()

    response = TestClient(application(service, Role.DISPATCHER)).post(
        "/api/v1/reviews/DEMO-TASK-101/decision",
        json={"decision": "APPROVE"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "AUTHORIZATION_DENIED"
    assert service.calls == []


def test_client_cannot_spoof_the_reviewer_identity() -> None:
    service = ReviewService()

    response = TestClient(application(service, Role.SUPERVISOR)).post(
        "/api/v1/reviews/DEMO-TASK-101/decision",
        json={"decision": "APPROVE", "reviewer": "伪造管理员"},
    )

    assert response.status_code == 422
    assert service.calls == []


def test_successful_decision_records_the_reviewer_and_decision_for_the_audit_center() -> None:
    class Recorder:
        def __init__(self) -> None:
            self.calls = []

        def record(self, request, **fields) -> None:
            self.calls.append((request, fields))

    service = ReviewService()
    app = application(service, Role.SUPERVISOR)
    recorder = Recorder()
    app.state.security_audit_recorder = recorder

    response = TestClient(app).post(
        "/api/v1/reviews/DEMO-TASK-101/decision",
        json={"decision": "REJECT", "reason": "信息不足"},
    )

    assert response.status_code == 200
    assert len(recorder.calls) == 1
    request, fields = recorder.calls[0]
    assert request.url.path == "/api/v1/reviews/DEMO-TASK-101/decision"
    assert fields["event_type"].value == "REVIEW_DECISION"
    assert fields["status"].value == "ALLOWED"
    assert fields["reason_code"] == "REVIEW_REJECTED"
    assert fields["principal"].subject_id == "test-supervisor"
    assert fields["permission"].value == "dispatch:review"


@pytest.mark.parametrize("reason", [None, "", " ", "单"])
def test_rejection_requires_a_meaningful_reason_before_calling_service(reason: str | None) -> None:
    service = ReviewService()

    response = TestClient(application(service, Role.SUPERVISOR)).post(
        "/api/v1/reviews/DEMO-TASK-101/decision",
        json={"decision": "REJECT", "reason": reason},
    )

    assert response.status_code == 422
    assert service.calls == []


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (ReviewNotFound(), 404, "REVIEW_NOT_FOUND"),
        (ReviewAlreadyDecided(), 409, "REVIEW_ALREADY_DECIDED"),
        (ReviewDispatchMissing(), 409, "REVIEW_DISPATCH_MISSING"),
        (ReviewVersionConflict(), 409, "DISPATCH_VERSION_CONFLICT"),
    ],
)
def test_review_domain_errors_have_stable_http_contract(error: Exception, status_code: int, code: str) -> None:
    response = TestClient(application(ReviewService(error=error), Role.ADMIN)).post(
        "/api/v1/reviews/DEMO-TASK-101/decision",
        json={"decision": "APPROVE"},
    )

    assert response.status_code == status_code
    assert response.json()["code"] == code
    assert "DEMO-TASK-101" not in response.text
