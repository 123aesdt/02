from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit import AuditRecord
from app.models.dispatch import Dispatch
from app.models.runtime_thread import RuntimeThread, RuntimeThreadEvent
from app.models.task import DispatchTask
from app.runtime_threads.identity import thread_id_for_persisted_task
from app.runtime_threads.models import RuntimeThreadEventType, RuntimeThreadStatus

IdempotencyState = Literal["NEW", "IN_PROGRESS", "TERMINAL"]
TERMINAL_STATUSES = frozenset({"APPROVED", "COMPLETED", "DLQ", "FAILED", "REVIEW_REQUIRED"})


class IdempotencyConflictError(Exception):
    """Raised when one idempotency key is reused by another task."""

    def __init__(self) -> None:
        super().__init__("Idempotency key is already assigned to a different task.")


@dataclass(frozen=True)
class IdempotencyDecision:
    state: IdempotencyState
    task_id: str
    idempotency_key: str
    existing_status: str | None
    should_execute: bool
    reason: str


@dataclass(frozen=True)
class ExecutionReconciliation:
    dispatch_id: int | None
    audit_id: int | None
    terminal_status: str | None

    @property
    def is_terminal(self) -> bool:
        return self.terminal_status in {"APPROVED", "REVIEW_REQUIRED"}


class IdempotencyService:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def begin(
        self,
        task_id: str,
        order_id: int,
        idempotency_key: str,
        *,
        anomaly_id: int | None = None,
        assignee_subject_id: str | None = None,
    ) -> IdempotencyDecision:
        with self._session_factory() as session:
            existing = self._existing(session, task_id, idempotency_key)
            if existing is not None:
                return self._decision(existing)

            task = DispatchTask(
                task_id=task_id,
                order_id=order_id,
                anomaly_id=anomaly_id,
                status="PENDING",
                idempotency_key=idempotency_key,
                assignee_subject_id=assignee_subject_id,
            )
            thread_id = thread_id_for_persisted_task(task_id)
            session.add(task)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                existing = self._existing(session, task_id, idempotency_key)
                if existing is None:
                    raise
                return self._decision(existing)
            runtime_thread = RuntimeThread(
                thread_id=thread_id,
                task_id=task_id,
                status=RuntimeThreadStatus.RUNNING.value,
                next_node="intake",
                state_version=0,
                checkpoint_count=0,
                resumed_count=0,
            )
            session.add(runtime_thread)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                existing = self._existing(session, task_id, idempotency_key)
                if existing is None:
                    raise
                return self._decision(existing)
            session.add(
                RuntimeThreadEvent(
                    event_id=str(uuid4()),
                    event_key="thread:created",
                    thread_id=thread_id,
                    event_type=RuntimeThreadEventType.THREAD_CREATED.value,
                    state_version=0,
                    metadata_json={},
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = self._existing(session, task_id, idempotency_key)
                if existing is None:
                    raise
                return self._decision(existing)
            return IdempotencyDecision("NEW", task_id, idempotency_key, None, True, "Ledger created.")

    def get(self, task_id: str, idempotency_key: str) -> IdempotencyDecision | None:
        with self._session_factory() as session:
            existing = self._existing(session, task_id, idempotency_key)
            return self._decision(existing) if existing is not None else None

    def mark_processing(self, task_id: str) -> None:
        self._set_status(task_id, "PROCESSING", started=True)

    def mark_terminal(self, task_id: str, status: str) -> None:
        self._set_status(task_id, status, completed=True)

    def reconcile_existing_execution(self, task_id: str) -> ExecutionReconciliation:
        with self._session_factory() as session:
            task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
            if task is None:
                return ExecutionReconciliation(None, None, None)
            dispatch = session.scalar(select(Dispatch).where(Dispatch.task_id == task.id))
            if dispatch is None:
                return ExecutionReconciliation(None, None, None)
            audit = session.scalar(
                select(AuditRecord).where(
                    AuditRecord.task_id == task.id,
                    AuditRecord.dispatch_id == dispatch.id,
                )
            )
            return ExecutionReconciliation(
                dispatch.id,
                audit.id if audit is not None else None,
                audit.result if audit is not None else None,
            )

    def _set_status(self, task_id: str, status: str, *, started: bool = False, completed: bool = False) -> None:
        with self._session_factory() as session:
            task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
            if task is None:
                raise ValueError("Dispatch task does not exist.")
            task.status = status
            if started:
                task.started_at = datetime.now(UTC)
            if completed:
                task.completed_at = datetime.now(UTC)
            session.commit()

    @staticmethod
    def _existing(session: Session, task_id: str, idempotency_key: str) -> DispatchTask | None:
        by_task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
        by_key = session.scalar(select(DispatchTask).where(DispatchTask.idempotency_key == idempotency_key))
        if by_task is not None and by_task.idempotency_key != idempotency_key:
            raise IdempotencyConflictError
        if by_key is not None and by_key.task_id != task_id:
            raise IdempotencyConflictError
        return by_task or by_key

    @staticmethod
    def _decision(task: DispatchTask) -> IdempotencyDecision:
        if task.status in TERMINAL_STATUSES:
            return IdempotencyDecision("TERMINAL", task.task_id, task.idempotency_key, task.status, False, "Task is terminal.")
        return IdempotencyDecision("IN_PROGRESS", task.task_id, task.idempotency_key, task.status, False, "Task already exists.")
