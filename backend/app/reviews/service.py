import json
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.models.audit import AuditRecord
from app.models.dispatch import Dispatch
from app.models.task import DispatchTask
from app.reviews.models import ReviewDecision, ReviewDecisionResult
from app.security.models import AuthenticatedPrincipal


class ReviewNotFound(Exception):
    """The requested dispatch task does not exist."""


class ReviewAlreadyDecided(Exception):
    """The task is no longer waiting for a manual decision."""


class ReviewDispatchMissing(Exception):
    """A review cannot be decided without its persisted dispatch proposal."""


class ReviewReasonRequired(Exception):
    """A rejection requires a meaningful reason."""


class ReviewVersionConflict(Exception):
    """Another reviewer changed the dispatch during this decision."""


class ReviewDecisionService:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def decide(
        self,
        task_id: str,
        decision: ReviewDecision,
        reason: str | None,
        principal: AuthenticatedPrincipal,
    ) -> ReviewDecisionResult:
        normalized_reason = self._reason(decision, reason)
        session = self._session_factory()
        try:
            task = session.scalar(
                select(DispatchTask).where(DispatchTask.task_id == task_id).with_for_update()
            )
            if task is None:
                raise ReviewNotFound
            if task.status != "REVIEW_REQUIRED":
                raise ReviewAlreadyDecided
            dispatch = session.scalar(
                select(Dispatch)
                .where(Dispatch.task_id == task.id)
                .order_by(Dispatch.id.desc())
                .limit(1)
                .with_for_update()
            )
            if dispatch is None:
                raise ReviewDispatchMissing

            decided_at = self._clock()
            if decided_at.tzinfo is None or decided_at.utcoffset() is None:
                raise ValueError("review decision clock must be timezone-aware")
            terminal_status = "APPROVED" if decision is ReviewDecision.APPROVE else "REJECTED"
            task.status = terminal_status
            task.completed_at = decided_at
            dispatch.status = terminal_status
            session.add(
                AuditRecord(
                    task_id=task.id,
                    dispatch_id=dispatch.id,
                    result=terminal_status,
                    reason=normalized_reason,
                    evidence_json=json.dumps(
                        {
                            "decision": decision.value,
                            "decided_at": decided_at.isoformat(),
                            "reviewer_display_name": principal.display_name,
                            "reviewer_subject_id": principal.subject_id,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
            )
            session.commit()
            return ReviewDecisionResult(
                task_id=task.task_id,
                decision=decision,
                status=terminal_status,
                reviewer=principal.display_name,
                decided_at=decided_at,
                dispatch_version=dispatch.version,
            )
        except StaleDataError as error:
            session.rollback()
            raise ReviewVersionConflict from error
        finally:
            session.close()

    @staticmethod
    def _reason(decision: ReviewDecision, reason: str | None) -> str:
        normalized = reason.strip() if reason is not None else ""
        if len(normalized) > 500:
            raise ValueError("review reason exceeds 500 characters")
        if decision is ReviewDecision.REJECT and len(normalized) < 2:
            raise ReviewReasonRequired
        if decision is ReviewDecision.APPROVE and not normalized:
            return "人工复核已批准。"
        return normalized
