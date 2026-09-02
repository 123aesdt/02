from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.models.runtime_thread import RuntimeThread, RuntimeThreadEvent
from app.models.task import DispatchTask
from app.runtime_threads.models import (
    BoundaryClaimConflict,
    PromoteCheckpoint,
    RuntimeThreadEventSnapshot,
    RuntimeThreadEventType,
    RuntimeThreadSnapshot,
    RuntimeThreadStatus,
    ThreadVersionConflict,
)


class SqlAlchemyRuntimeThreadRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def create_for_task(self, task_id: str, thread_id: str) -> RuntimeThreadSnapshot:
        with self._session_factory() as session:
            existing = session.scalar(select(RuntimeThread).where(RuntimeThread.task_id == task_id))
            if existing is not None:
                if existing.thread_id != thread_id:
                    raise ThreadVersionConflict("Dispatch task is already assigned to another runtime thread.")
                return self._thread_snapshot(existing)
            if session.scalar(select(DispatchTask.id).where(DispatchTask.task_id == task_id)) is None:
                raise LookupError(f"Unknown dispatch task: {task_id}")
            row = RuntimeThread(
                thread_id=thread_id,
                task_id=task_id,
                status=RuntimeThreadStatus.RUNNING.value,
                next_node="intake",
                state_version=0,
                checkpoint_count=0,
                resumed_count=0,
            )
            session.add(row)
            session.add(self.created_event(thread_id))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(select(RuntimeThread).where(RuntimeThread.task_id == task_id))
                if existing is None or existing.thread_id != thread_id:
                    raise
                return self._thread_snapshot(existing)
            return self._thread_snapshot(row)

    @staticmethod
    def created_event(thread_id: str) -> RuntimeThreadEvent:
        return RuntimeThreadEvent(
            event_id=str(uuid4()),
            event_key="thread:created",
            thread_id=thread_id,
            event_type=RuntimeThreadEventType.THREAD_CREATED.value,
            state_version=0,
            metadata_json={},
        )

    def get_by_thread_id(self, thread_id: str) -> RuntimeThreadSnapshot | None:
        with self._session_factory() as session:
            row = session.scalar(select(RuntimeThread).where(RuntimeThread.thread_id == thread_id))
            return self._thread_snapshot(row) if row is not None else None

    def get_by_task_id(self, task_id: str) -> RuntimeThreadSnapshot | None:
        with self._session_factory() as session:
            row = session.scalar(select(RuntimeThread).where(RuntimeThread.task_id == task_id))
            return self._thread_snapshot(row) if row is not None else None

    def claim_override_boundary(
        self,
        thread_id: str,
        *,
        expected_checkpoint_id: str,
        expected_state_version: int,
        expected_next_node: str,
    ) -> RuntimeThreadSnapshot:
        return self._claim_boundary(
            thread_id,
            expected_checkpoint_id=expected_checkpoint_id,
            expected_state_version=expected_state_version,
            expected_next_node=expected_next_node,
            target_status=RuntimeThreadStatus.OVERRIDING,
            worker_consumer=None,
        )

    def claim_next_node(
        self,
        thread_id: str,
        *,
        expected_checkpoint_id: str,
        expected_state_version: int,
        expected_next_node: str,
        worker_consumer: str,
    ) -> RuntimeThreadSnapshot:
        return self._claim_boundary(
            thread_id,
            expected_checkpoint_id=expected_checkpoint_id,
            expected_state_version=expected_state_version,
            expected_next_node=expected_next_node,
            target_status=RuntimeThreadStatus.RUNNING,
            worker_consumer=worker_consumer,
        )

    def release_override_boundary(
        self,
        thread_id: str,
        *,
        expected_checkpoint_id: str,
        expected_state_version: int,
        expected_next_node: str,
    ) -> RuntimeThreadSnapshot:
        with self._session_factory() as session:
            result = session.execute(
                update(RuntimeThread)
                .where(
                    RuntimeThread.thread_id == thread_id,
                    RuntimeThread.status == RuntimeThreadStatus.OVERRIDING.value,
                    RuntimeThread.current_checkpoint_id == expected_checkpoint_id,
                    RuntimeThread.state_version == expected_state_version,
                    RuntimeThread.next_node == expected_next_node,
                )
                .values(
                    status=RuntimeThreadStatus.STABLE.value,
                    row_version=RuntimeThread.row_version + 1,
                )
            )
            if result.rowcount != 1:
                session.rollback()
                raise BoundaryClaimConflict("RUNTIME_BOUNDARY_RELEASE_CONFLICT")
            session.commit()
            return self._thread_snapshot(self._required_thread(session, thread_id))

    def _claim_boundary(
        self,
        thread_id: str,
        *,
        expected_checkpoint_id: str,
        expected_state_version: int,
        expected_next_node: str,
        target_status: RuntimeThreadStatus,
        worker_consumer: str | None,
    ) -> RuntimeThreadSnapshot:
        values: dict[str, object] = {
            "status": target_status.value,
            "row_version": RuntimeThread.row_version + 1,
        }
        if worker_consumer is not None:
            values["worker_consumer"] = worker_consumer
        with self._session_factory() as session:
            result = session.execute(
                update(RuntimeThread)
                .where(
                    RuntimeThread.thread_id == thread_id,
                    RuntimeThread.status == RuntimeThreadStatus.STABLE.value,
                    RuntimeThread.current_checkpoint_id == expected_checkpoint_id,
                    RuntimeThread.state_version == expected_state_version,
                    RuntimeThread.next_node == expected_next_node,
                )
                .values(**values)
            )
            if result.rowcount != 1:
                session.rollback()
                raise BoundaryClaimConflict("RUNTIME_BOUNDARY_CLAIM_CONFLICT")
            session.commit()
            return self._thread_snapshot(self._required_thread(session, thread_id))

    def stage_checkpoint(self, command: PromoteCheckpoint) -> RuntimeThreadEventSnapshot:
        event_key = f"staged:{command.checkpoint_id}"
        with self._session_factory() as session:
            existing = self._event_by_key(session, command.thread_id, event_key)
            if existing is not None:
                return self._event_snapshot(existing)
            if session.scalar(select(RuntimeThread.id).where(RuntimeThread.thread_id == command.thread_id)) is None:
                raise LookupError(f"Unknown runtime thread: {command.thread_id}")
            event = self._checkpoint_event(command, RuntimeThreadEventType.CHECKPOINT_STAGED, event_key)
            session.add(event)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = self._event_by_key(session, command.thread_id, event_key)
                if existing is None:
                    raise
                return self._event_snapshot(existing)
            return self._event_snapshot(event)

    def promote_checkpoint(self, command: PromoteCheckpoint) -> RuntimeThreadSnapshot:
        with self._session_factory() as session:
            row = self._required_thread(session, command.thread_id)
            if row.current_checkpoint_id == command.checkpoint_id:
                return self._thread_snapshot(row)
            if row.status == RuntimeThreadStatus.TERMINAL.value:
                raise ThreadVersionConflict("Terminal runtime thread cannot advance.")
            if row.current_checkpoint_id != command.expected_checkpoint_id or row.state_version != command.expected_state_version:
                raise ThreadVersionConflict("Runtime thread checkpoint compare-and-swap failed.")
            row.current_checkpoint_id = command.checkpoint_id
            row.state_version += 1
            row.current_node = command.node
            row.next_node = command.next_node
            row.checkpoint_count += 1
            row.checkpoint_size_bytes = command.checkpoint_size_bytes
            row.worker_consumer = command.worker_consumer
            row.status = RuntimeThreadStatus.STABLE.value
            session.add(self._checkpoint_event(command, command.event_type, command.event_key))
            try:
                session.commit()
            except (IntegrityError, StaleDataError) as error:
                session.rollback()
                current = self._required_thread(session, command.thread_id)
                if current.current_checkpoint_id == command.checkpoint_id:
                    return self._thread_snapshot(current)
                raise ThreadVersionConflict("Runtime thread checkpoint compare-and-swap failed.") from error
            return self._thread_snapshot(row)

    def mark_resumed(self, thread_id: str, event_key: str, worker_consumer: str) -> RuntimeThreadSnapshot:
        with self._session_factory() as session:
            row = self._required_thread(session, thread_id)
            if row.status == RuntimeThreadStatus.TERMINAL.value:
                return self._thread_snapshot(row)
            if self._event_by_key(session, thread_id, event_key) is not None:
                return self._thread_snapshot(row)
            row.resumed_count += 1
            row.worker_consumer = worker_consumer
            session.add(
                RuntimeThreadEvent(
                    event_id=str(uuid4()),
                    event_key=event_key,
                    thread_id=thread_id,
                    event_type=RuntimeThreadEventType.THREAD_RESUMED.value,
                    checkpoint_id=row.current_checkpoint_id,
                    state_version=row.state_version,
                    node=row.current_node,
                    next_node=row.next_node,
                    worker_consumer=worker_consumer,
                    metadata_json={},
                )
            )
            session.commit()
            return self._thread_snapshot(row)

    def mark_terminal(
        self,
        thread_id: str,
        *,
        event_key: str,
        worker_consumer: str,
        current_node: str | None,
        error_code: str | None = None,
    ) -> RuntimeThreadSnapshot:
        with self._session_factory() as session:
            row = self._required_thread(session, thread_id)
            if self._event_by_key(session, thread_id, event_key) is not None:
                return self._thread_snapshot(row)
            row.status = RuntimeThreadStatus.TERMINAL.value
            row.current_node = current_node
            row.next_node = None
            row.worker_consumer = worker_consumer
            row.terminal_at = datetime.now(UTC)
            session.add(
                RuntimeThreadEvent(
                    event_id=str(uuid4()),
                    event_key=event_key,
                    thread_id=thread_id,
                    event_type=RuntimeThreadEventType.THREAD_TERMINAL.value,
                    checkpoint_id=row.current_checkpoint_id,
                    state_version=row.state_version,
                    node=current_node,
                    worker_consumer=worker_consumer,
                    error_code=error_code,
                    metadata_json={},
                )
            )
            session.commit()
            return self._thread_snapshot(row)

    def update_last_event_sequence(self, thread_id: str, sequence: int) -> RuntimeThreadSnapshot:
        with self._session_factory() as session:
            row = self._required_thread(session, thread_id)
            if row.last_event_sequence is None or sequence > row.last_event_sequence:
                row.last_event_sequence = sequence
                session.commit()
            return self._thread_snapshot(row)

    def list_events(self, thread_id: str, limit: int) -> Sequence[RuntimeThreadEventSnapshot]:
        if limit <= 0:
            return []
        with self._session_factory() as session:
            rows = list(
                session.scalars(
                    select(RuntimeThreadEvent)
                    .where(RuntimeThreadEvent.thread_id == thread_id)
                    .order_by(RuntimeThreadEvent.id.desc())
                    .limit(limit)
                ).all()
            )
            return [self._event_snapshot(row) for row in reversed(rows)]

    @staticmethod
    def _checkpoint_event(
        command: PromoteCheckpoint,
        event_type: RuntimeThreadEventType,
        event_key: str,
    ) -> RuntimeThreadEvent:
        return RuntimeThreadEvent(
            event_id=str(uuid4()),
            event_key=event_key,
            thread_id=command.thread_id,
            event_type=event_type.value,
            checkpoint_id=command.checkpoint_id,
            parent_checkpoint_id=command.parent_checkpoint_id,
            state_version=command.expected_state_version + 1,
            node=command.node,
            next_node=command.next_node,
            checkpoint_size_bytes=command.checkpoint_size_bytes,
            worker_consumer=command.worker_consumer,
            metadata_json={},
        )

    @staticmethod
    def _required_thread(session: Session, thread_id: str) -> RuntimeThread:
        row = session.scalar(select(RuntimeThread).where(RuntimeThread.thread_id == thread_id))
        if row is None:
            raise LookupError(f"Unknown runtime thread: {thread_id}")
        return row

    @staticmethod
    def _event_by_key(session: Session, thread_id: str, event_key: str) -> RuntimeThreadEvent | None:
        return session.scalar(
            select(RuntimeThreadEvent).where(
                RuntimeThreadEvent.thread_id == thread_id,
                RuntimeThreadEvent.event_key == event_key,
            )
        )

    @staticmethod
    def _thread_snapshot(row: RuntimeThread) -> RuntimeThreadSnapshot:
        return RuntimeThreadSnapshot(
            thread_id=row.thread_id,
            task_id=row.task_id,
            status=RuntimeThreadStatus(row.status),
            current_checkpoint_id=row.current_checkpoint_id,
            state_version=row.state_version,
            current_node=row.current_node,
            next_node=row.next_node,
            checkpoint_count=row.checkpoint_count,
            checkpoint_size_bytes=row.checkpoint_size_bytes,
            last_event_sequence=row.last_event_sequence,
            worker_consumer=row.worker_consumer,
            resumed_count=row.resumed_count,
            created_at=row.created_at,
            updated_at=row.updated_at,
            terminal_at=row.terminal_at,
            row_version=row.row_version,
        )

    @staticmethod
    def _event_snapshot(row: RuntimeThreadEvent) -> RuntimeThreadEventSnapshot:
        return RuntimeThreadEventSnapshot(
            event_id=row.event_id,
            event_key=row.event_key,
            thread_id=row.thread_id,
            event_type=RuntimeThreadEventType(row.event_type),
            checkpoint_id=row.checkpoint_id,
            parent_checkpoint_id=row.parent_checkpoint_id,
            state_version=row.state_version,
            node=row.node,
            next_node=row.next_node,
            checkpoint_size_bytes=row.checkpoint_size_bytes,
            worker_consumer=row.worker_consumer,
            error_code=row.error_code,
            metadata=dict(row.metadata_json),
            created_at=row.created_at,
        )
