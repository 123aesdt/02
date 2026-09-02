from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.api.v1.schemas import CreateDispatchTaskRequest
from app.events.broker import TaskEventBroker
from app.events.models import TaskEvent, TaskEventType
from app.idempotency.service import IdempotencyService
from app.models.audit import AuditRecord
from app.models.demo_employee_account import DemoEmployeeAccount
from app.models.dispatch import Dispatch
from app.models.dispatch_publication import DispatchPublication
from app.models.task import DispatchTask
from app.observability.context import current_correlation_id
from app.streams.errors import QueueConnectionError
from app.streams.models import DispatchTaskMessage
from app.streams.redis_queue import RedisStreamQueue


class TaskNotFoundError(Exception):
    pass


class IdempotencyConflictError(Exception):
    pass


class SubmissionQueueError(Exception):
    pass


class AssigneeNotFoundError(Exception):
    pass


class TaskAccessForbiddenError(Exception):
    pass


class DispatchTaskApiService:
    def __init__(self, session_factory, queue: RedisStreamQueue, *, event_broker: TaskEventBroker | None = None) -> None:
        self._session_factory = session_factory
        self._queue = queue
        self._idempotency = IdempotencyService(session_factory)
        self._event_broker = event_broker

    async def submit(
        self,
        request: CreateDispatchTaskRequest,
        *,
        assignee_subject_id: str,
    ) -> dict[str, object]:
        if request.assignee_employee_id is not None:
            self._require_active_delivery_employee(assignee_subject_id)
        existing = self._by_key(request.idempotency_key)
        if existing is not None:
            if (
                existing.order_id != request.order_id
                or existing.assignee_subject_id != assignee_subject_id
            ):
                raise IdempotencyConflictError
            if existing.status == "SUBMISSION_FAILED":
                return await self._publish_existing(existing, request)
            return self._accepted(existing, duplicate=True)
        task_id = f"TASK-{uuid4().hex[:31]}"
        decision = self._idempotency.begin(
            task_id,
            request.order_id,
            request.idempotency_key,
            anomaly_id=request.anomaly_id,
            assignee_subject_id=assignee_subject_id,
        )
        if not decision.should_execute:
            return self._accepted(self._task(decision.task_id), duplicate=True)
        message = DispatchTaskMessage(
            "1",
            task_id,
            request.order_id,
            request.anomaly_id,
            request.idempotency_key,
            datetime.now(UTC).isoformat(),
            {
                "driver_id": request.driver_id,
                "vehicle_id": request.vehicle_id,
                "route_id": request.route_id,
                "anomaly_type": request.anomaly_type,
                "anomaly_description": request.anomaly_description,
                "vehicle_status": request.vehicle_status,
            },
            current_correlation_id(),
        )
        try:
            await self._queue.publish(message)
        except QueueConnectionError as error:
            self._idempotency.mark_terminal(task_id, "SUBMISSION_FAILED")
            raise SubmissionQueueError from error
        await self._publish_accepted(task_id)
        return self._accepted(self._task(task_id), duplicate=False)

    async def _publish_existing(self, task: DispatchTask, request: CreateDispatchTaskRequest) -> dict[str, object]:
        message = DispatchTaskMessage(
            "1",
            task.task_id,
            task.order_id,
            request.anomaly_id,
            task.idempotency_key,
            datetime.now(UTC).isoformat(),
            {
                "driver_id": request.driver_id,
                "vehicle_id": request.vehicle_id,
                "route_id": request.route_id,
                "anomaly_type": request.anomaly_type,
                "anomaly_description": request.anomaly_description,
                "vehicle_status": request.vehicle_status,
            },
            current_correlation_id(),
        )
        try:
            await self._queue.publish(message)
        except QueueConnectionError as error:
            raise SubmissionQueueError from error
        self._set_submission_pending(task.task_id)
        await self._publish_accepted(task.task_id)
        return self._accepted(self._task(task.task_id), duplicate=True)

    async def _publish_accepted(self, task_id: str) -> None:
        if self._event_broker is None:
            return
        try:
            await self._event_broker.publish(TaskEvent.create(task_id, TaskEventType.TASK_ACCEPTED, "api", "PENDING"))
        except Exception:
            return

    def status(self, task_id: str) -> dict[str, object]:
        task = self._task(task_id)
        status = self._api_status(task.status)
        return {
            "task_id": task.task_id,
            "order_id": task.order_id,
            "status": status,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "created_at": task.created_at,
            "ready": status in {"COMPLETED", "REVIEW_REQUIRED"},
            "requires_manual_review": status == "REVIEW_REQUIRED",
        }

    def result(self, task_id: str, *, include_unpublished: bool = True) -> dict[str, object]:
        task = self._task(task_id)
        status = self._api_status(task.status)
        if task.status not in {"APPROVED", "COMPLETED", "REVIEW_REQUIRED"}:
            return {"task_id": task.task_id, "order_id": task.order_id, "ready": False, "status": status}
        with self._session_factory() as session:
            dispatch = session.scalar(select(Dispatch).where(Dispatch.task_id == task.id))
            audit = session.scalar(select(AuditRecord).where(AuditRecord.task_id == task.id))
            publication = session.scalar(
                select(DispatchPublication).where(DispatchPublication.task_id == task.id)
            )
            recipient = None
            if task.assignee_subject_id is not None:
                recipient = session.get(DemoEmployeeAccount, task.assignee_subject_id)
            recipient_employee_id = task.assignee_subject_id
            recipient_display_name = (
                recipient.display_name
                if recipient is not None
                else task.assignee_subject_id
            )
            route_visible = include_unpublished or publication is not None
            return {
                "task_id": task.task_id,
                "order_id": task.order_id,
                "ready": True,
                "status": status,
                "dispatch": None
                if dispatch is None
                else {
                    "dispatch_id": dispatch.id,
                    "dispatch_no": dispatch.dispatch_no,
                    "original_route_id": dispatch.original_route_id,
                    "target_route_id": dispatch.target_route_id if route_visible else None,
                    "decision_reason": dispatch.decision_reason if route_visible else None,
                    "fallback_used": dispatch.fallback_used,
                    "fallback_reason": dispatch.fallback_reason,
                    "version": dispatch.version,
                    "status": dispatch.status,
                    "executed": dispatch.status in {"EXECUTED", "COMPLETED", "KEPT_ROUTE", "REROUTED"},
                },
                "audit": None
                if audit is None
                else {
                    "result": audit.result,
                    "reason": audit.reason,
                    "dispatch_id": audit.dispatch_id,
                    "created_at": audit.created_at,
                },
                "publication": {
                    "status": "PENDING" if publication is None else publication.status,
                    "route_id": None if publication is None else publication.route_id,
                    "route_instruction": None if publication is None else publication.route_instruction,
                    "published_at": None if publication is None else self._aware(publication.published_at),
                    "published_by": None if publication is None else publication.published_by_display_name,
                    "recipient_employee_id": recipient_employee_id,
                    "recipient_display_name": recipient_display_name,
                },
            }

    def require_read_access(
        self,
        task_id: str,
        *,
        subject_id: str,
        can_read_all: bool,
    ) -> None:
        task = self._task(task_id)
        if not can_read_all and task.assignee_subject_id != subject_id:
            raise TaskAccessForbiddenError

    def _require_active_delivery_employee(self, employee_id: str) -> None:
        with self._session_factory() as session:
            account = session.get(DemoEmployeeAccount, employee_id)
            if account is None or not account.is_active or account.role != "EMPLOYEE":
                raise AssigneeNotFoundError

    def _by_key(self, key: str) -> DispatchTask | None:
        with self._session_factory() as session:
            return session.scalar(select(DispatchTask).where(DispatchTask.idempotency_key == key))

    def _task(self, task_id: str) -> DispatchTask:
        with self._session_factory() as session:
            task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
            if task is None:
                raise TaskNotFoundError
            return task

    def _set_submission_pending(self, task_id: str) -> None:
        with self._session_factory() as session:
            task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
            if task is None:
                raise TaskNotFoundError
            task.status = "PENDING"
            task.completed_at = None
            session.commit()

    @staticmethod
    def _accepted(task: DispatchTask, *, duplicate: bool) -> dict[str, object]:
        return {
            "task_id": task.task_id,
            "order_id": task.order_id,
            "status": task.status,
            "accepted": True,
            "duplicate": duplicate,
            "message": "Dispatch task accepted for asynchronous processing.",
        }

    @staticmethod
    def _api_status(status: str) -> str:
        return "COMPLETED" if status == "APPROVED" else status

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None or value.utcoffset() is None else value
