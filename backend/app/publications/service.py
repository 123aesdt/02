from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit import AuditRecord
from app.models.demo_employee_account import DemoEmployeeAccount
from app.models.dispatch import Dispatch
from app.models.dispatch_publication import DispatchPublication
from app.models.order import Order
from app.models.task import DispatchTask
from app.security.models import AuthenticatedPrincipal


class PublicationTaskNotFound(Exception):
    """The requested task does not exist."""


class PublicationDispatchMissing(Exception):
    """The task does not have a persisted dispatch proposal."""


class PublicationNotApproved(Exception):
    """The latest dispatch has not passed audit approval."""


class PublicationRouteMissing(Exception):
    """The approved dispatch does not contain a route to publish."""


class DispatchPublicationService:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def publish(self, task_id: str, principal: AuthenticatedPrincipal) -> dict[str, object]:
        return self._publish(task_id, principal.subject_id, principal.display_name)

    def publish_automatically(self, task_id: str) -> dict[str, object]:
        return self._publish(
            task_id,
            "countyflow-ai",
            "CountyFlow AI 自动发布",
        )

    def _publish(
        self,
        task_id: str,
        published_by_subject_id: str,
        published_by_display_name: str,
    ) -> dict[str, object]:
        session = self._session_factory()
        try:
            task = session.scalar(
                select(DispatchTask).where(DispatchTask.task_id == task_id).with_for_update()
            )
            if task is None:
                raise PublicationTaskNotFound
            existing = session.scalar(
                select(DispatchPublication).where(DispatchPublication.task_id == task.id)
            )
            if existing is not None:
                return self._result(session, task, existing, duplicate=True)

            dispatch = session.scalar(
                select(Dispatch)
                .where(Dispatch.task_id == task.id)
                .order_by(Dispatch.id.desc())
                .limit(1)
                .with_for_update()
            )
            if dispatch is None:
                raise PublicationDispatchMissing
            audit = session.scalar(
                select(AuditRecord)
                .where(AuditRecord.task_id == task.id, AuditRecord.dispatch_id == dispatch.id)
                .order_by(AuditRecord.id.desc())
                .limit(1)
            )
            if task.status not in {"APPROVED", "COMPLETED"} or audit is None or audit.result != "APPROVED":
                raise PublicationNotApproved
            route_id = dispatch.target_route_id or dispatch.original_route_id
            if route_id is None:
                raise PublicationRouteMissing
            order = session.get(Order, task.order_id)
            if order is None:
                raise PublicationTaskNotFound
            published_at = self._aware(self._clock())
            publication = DispatchPublication(
                task_id=task.id,
                dispatch_id=dispatch.id,
                status="PUBLISHED",
                route_id=route_id,
                route_instruction=(
                    f"从 {order.origin} 出发，按 {route_id} 行驶，前往 {order.destination}。"
                    "途中注意现场路况并服从安全调度。"
                ),
                published_by_subject_id=published_by_subject_id,
                published_by_display_name=published_by_display_name,
                published_at=published_at,
            )
            session.add(publication)
            session.commit()
            return self._result(session, task, publication, duplicate=False)
        except IntegrityError:
            session.rollback()
            task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
            publication = None if task is None else session.scalar(
                select(DispatchPublication).where(DispatchPublication.task_id == task.id)
            )
            if task is None or publication is None:
                raise
            return self._result(session, task, publication, duplicate=True)
        finally:
            session.close()

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("publication clock must be timezone-aware")
        return value

    @staticmethod
    def _result(
        session: Session,
        task: DispatchTask,
        publication: DispatchPublication,
        *,
        duplicate: bool,
    ) -> dict[str, object]:
        published_at = publication.published_at
        if published_at.tzinfo is None or published_at.utcoffset() is None:
            published_at = published_at.replace(tzinfo=UTC)
        recipient = None
        if task.assignee_subject_id is not None:
            recipient = session.get(DemoEmployeeAccount, task.assignee_subject_id)
        recipient_employee_id = task.assignee_subject_id or "UNASSIGNED"
        recipient_display_name = (
            recipient.display_name
            if recipient is not None
            else task.assignee_subject_id or "未指定接收员工"
        )
        return {
            "task_id": task.task_id,
            "dispatch_id": publication.dispatch_id,
            "status": publication.status,
            "route_id": publication.route_id,
            "route_instruction": publication.route_instruction,
            "published_at": published_at,
            "published_by": publication.published_by_display_name,
            "recipient_employee_id": recipient_employee_id,
            "recipient_display_name": recipient_display_name,
            "duplicate": duplicate,
        }
