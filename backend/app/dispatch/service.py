from collections.abc import Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dispatch.models import DispatchResult
from app.models.dispatch import Dispatch
from app.models.task import DispatchTask
from app.repositories.dispatch import DispatchRepository


class DispatchService:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def execute(
        self,
        task_id: str,
        order_id: int,
        original_route_id: str,
        target_route_id: str | None,
        decision: str,
        decision_reason: str,
        fallback_used: bool,
        fallback_reason: str | None,
        requires_manual_review: bool,
        recommended_action: str | None = None,
        analysis_mode: str | None = None,
        issue_subtype: str | None = None,
    ) -> DispatchResult:
        with self._session_factory() as session:
            task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
            if task is None:
                raise ValueError("Dispatch task does not exist")
            existing = DispatchRepository(session).get_by_task_id(task.id)
            if existing is not None:
                existing_requires_manual_review = existing.status == "REVIEW_REQUIRED"
                return DispatchResult(
                    existing.id,
                    existing.dispatch_no,
                    order_id,
                    task_id,
                    existing.status,
                    existing.original_route_id or original_route_id,
                    existing.target_route_id,
                    existing.version,
                    not existing_requires_manual_review,
                    existing.decision_reason or decision_reason,
                    existing_requires_manual_review,
                )
            manual_review = requires_manual_review or decision in {"MANUAL_REVIEW", "NO_SAFE_ROUTE"}
            status = "REVIEW_REQUIRED" if manual_review else "REROUTED" if decision == "REROUTE" else "KEPT_ROUTE"
            dispatch = Dispatch(
                dispatch_no=f"DSP-{uuid4().hex}",
                order_id=order_id,
                task_id=task.id,
                original_route_id=original_route_id,
                target_route_id=target_route_id if manual_review else target_route_id or original_route_id,
                decision_reason=decision_reason,
                recommended_action=recommended_action or ("保持任务暂停并等待人工复核。" if manual_review else None),
                analysis_mode=analysis_mode or ("EIGHT_AGENT_RULE_ASSISTED" if manual_review else None),
                issue_subtype=issue_subtype or ("GENERAL" if manual_review else None),
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                status=status,
            )
            session.add(dispatch)
            DispatchRepository(session).commit_dispatch(dispatch)
            return DispatchResult(
                dispatch.id,
                dispatch.dispatch_no,
                order_id,
                task_id,
                status,
                original_route_id,
                dispatch.target_route_id,
                dispatch.version,
                not manual_review,
                decision_reason,
                manual_review,
            )
