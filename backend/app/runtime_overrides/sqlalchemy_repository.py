from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.runtime_override import RuntimeOverride, RuntimeOverrideAttempt
from app.models.runtime_thread import RuntimeThread, RuntimeThreadEvent
from app.runtime_overrides.models import (
    RuntimeOverrideCommand,
    RuntimeOverrideDecision,
    RuntimeOverrideIdempotencyConflict,
    RuntimeOverrideStatus,
    StoredRuntimeOverride,
)
from app.runtime_threads.models import RuntimeThreadEventType, RuntimeThreadStatus, ThreadVersionConflict


class SqlAlchemyRuntimeOverrideRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def begin_or_replay(
        self,
        command: RuntimeOverrideCommand,
        fingerprint: str,
        *,
        intent_expires_at: datetime,
    ) -> StoredRuntimeOverride:
        with self._session_factory() as session:
            existing = session.scalar(
                select(RuntimeOverride).where(RuntimeOverride.idempotency_key == command.idempotency_key)
            )
            if existing is not None:
                return self._replay(existing, command, fingerprint)
            thread = session.scalar(select(RuntimeThread).where(RuntimeThread.thread_id == command.thread_id))
            if thread is None:
                raise LookupError(command.thread_id)
            row = RuntimeOverride(
                override_id=command.override_id,
                thread_id=command.thread_id,
                task_id=thread.task_id,
                operator_id=command.operator_id,
                operator_role=command.operator_role,
                idempotency_key=command.idempotency_key,
                payload_fingerprint=fingerprint,
                expected_version=command.expected_version,
                expected_next_node=command.expected_next_node,
                entity_type=command.entity_type,
                entity_id=command.entity_id,
                field_name=command.field,
                old_value_json=command.old_value,
                new_value_json=command.new_value,
                reason=command.reason,
                status=RuntimeOverrideStatus.PENDING.value,
                event_status="PENDING",
                intent_expires_at=intent_expires_at,
                requested_at=command.requested_at,
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(RuntimeOverride).where(RuntimeOverride.idempotency_key == command.idempotency_key)
                )
                if existing is None:
                    raise
                return self._replay(existing, command, fingerprint)
            return self._snapshot(row)

    def append_attempt(
        self,
        override_id: str,
        *,
        operation: str,
        status: str,
        started_at: datetime,
    ) -> int:
        with self._session_factory() as session:
            if session.scalar(select(RuntimeOverride.id).where(RuntimeOverride.override_id == override_id)) is None:
                raise LookupError(override_id)
            attempt_no = int(
                session.scalar(
                    select(func.coalesce(func.max(RuntimeOverrideAttempt.attempt_no), 0)).where(
                        RuntimeOverrideAttempt.override_id == override_id
                    )
                )
                or 0
            ) + 1
            session.add(
                RuntimeOverrideAttempt(
                    attempt_id=str(uuid4()),
                    override_id=override_id,
                    attempt_no=attempt_no,
                    operation=operation,
                    status=status,
                    started_at=started_at,
                )
            )
            session.commit()
            return attempt_no

    def mark_applying(
        self,
        override_id: str,
        *,
        before_state_version: int,
        source_checkpoint_id: str,
        started_at: datetime,
    ) -> StoredRuntimeOverride:
        with self._session_factory() as session:
            row = self._required(session, override_id)
            if row.status == RuntimeOverrideStatus.APPLYING.value:
                return self._snapshot(row)
            if row.status != RuntimeOverrideStatus.PENDING.value:
                raise RuntimeError("RUNTIME_OVERRIDE_INVALID_TRANSITION")
            row.status = RuntimeOverrideStatus.APPLYING.value
            row.decision = RuntimeOverrideDecision.ALLOWED.value
            row.before_state_version = before_state_version
            row.source_checkpoint_id = source_checkpoint_id
            row.started_at = started_at
            session.add(
                RuntimeOverrideAttempt(
                    attempt_id=str(uuid4()),
                    override_id=override_id,
                    attempt_no=1,
                    operation="APPLY",
                    status=RuntimeOverrideStatus.APPLYING.value,
                    observed_state_version=before_state_version,
                    source_checkpoint_id=source_checkpoint_id,
                    started_at=started_at,
                )
            )
            session.commit()
            return self._snapshot(row)

    def attach_result_checkpoint(self, override_id: str, checkpoint_id: str) -> StoredRuntimeOverride:
        with self._session_factory() as session:
            row = self._required(session, override_id)
            if row.status != RuntimeOverrideStatus.APPLYING.value:
                raise RuntimeError("RUNTIME_OVERRIDE_INVALID_TRANSITION")
            if row.result_checkpoint_id is not None and row.result_checkpoint_id != checkpoint_id:
                raise RuntimeError("RUNTIME_OVERRIDE_RESULT_CONFLICT")
            row.result_checkpoint_id = checkpoint_id
            attempt = self._latest_attempt(session, override_id)
            if attempt is not None:
                attempt.result_checkpoint_id = checkpoint_id
            session.commit()
            return self._snapshot(row)

    def finish(
        self,
        override_id: str,
        *,
        status: RuntimeOverrideStatus,
        decision: RuntimeOverrideDecision,
        error_code: str,
        completed_at: datetime,
    ) -> StoredRuntimeOverride:
        if status not in {
            RuntimeOverrideStatus.REJECTED,
            RuntimeOverrideStatus.CONFLICT,
            RuntimeOverrideStatus.FAILED,
        }:
            raise ValueError("invalid final override status")
        with self._session_factory() as session:
            row = self._required(session, override_id)
            if row.status == RuntimeOverrideStatus.APPLIED.value:
                return self._snapshot(row)
            row.status = status.value
            row.decision = decision.value
            row.error_code = error_code
            row.error_summary = error_code
            row.completed_at = completed_at
            attempt = self._latest_attempt(session, override_id)
            if attempt is not None:
                attempt.status = status.value
                attempt.error_code = error_code
                attempt.error_summary = error_code
                attempt.completed_at = completed_at
            session.commit()
            return self._snapshot(row)

    def mark_partial(self, override_id: str, *, error_code: str, completed_at: datetime) -> StoredRuntimeOverride:
        with self._session_factory() as session:
            row = self._required(session, override_id)
            if row.status == RuntimeOverrideStatus.APPLIED.value:
                return self._snapshot(row)
            row.status = RuntimeOverrideStatus.PARTIAL.value
            row.error_code = error_code
            row.error_summary = error_code
            row.completed_at = completed_at
            attempt = self._latest_attempt(session, override_id)
            if attempt is not None:
                attempt.status = RuntimeOverrideStatus.PARTIAL.value
                attempt.error_code = error_code
                attempt.error_summary = error_code
                attempt.completed_at = completed_at
            session.commit()
            return self._snapshot(row)

    def mark_event_status(self, override_id: str, event_status: str) -> StoredRuntimeOverride:
        if event_status not in {"PENDING", "PUBLISHED", "FAILED"}:
            raise ValueError("invalid event status")
        with self._session_factory() as session:
            row = self._required(session, override_id)
            row.event_status = event_status
            session.commit()
            return self._snapshot(row)

    def record_timings(self, override_id: str, **timings_ms: float) -> None:
        allowed = {
            "authorization_ms",
            "lock_ms",
            "checkpoint_read_ms",
            "state_update_ms",
            "promotion_ms",
            "total_ms",
        }
        if set(timings_ms) - allowed:
            raise ValueError("unknown runtime override timing")
        with self._session_factory() as session:
            attempt = self._latest_attempt(session, override_id)
            if attempt is None:
                return
            for name, value in timings_ms.items():
                setattr(attempt, name, Decimal(str(round(value, 3))))
            session.commit()

    def promote_applied(
        self,
        override_id: str,
        *,
        result_checkpoint_id: str,
        checkpoint_size_bytes: int,
        completed_at: datetime,
    ) -> StoredRuntimeOverride:
        with self._session_factory() as session:
            row = self._required(session, override_id)
            if row.status == RuntimeOverrideStatus.APPLIED.value:
                return self._snapshot(row)
            thread = session.scalar(select(RuntimeThread).where(RuntimeThread.thread_id == row.thread_id))
            if thread is None:
                raise LookupError(row.thread_id)
            if (
                row.status not in {RuntimeOverrideStatus.APPLYING.value, RuntimeOverrideStatus.PARTIAL.value}
                or row.result_checkpoint_id != result_checkpoint_id
                or thread.status != RuntimeThreadStatus.OVERRIDING.value
                or thread.current_checkpoint_id != row.source_checkpoint_id
                or thread.state_version != row.expected_version
                or thread.next_node != row.expected_next_node
            ):
                raise ThreadVersionConflict("Runtime override canonical promotion compare-and-swap failed.")
            thread.current_checkpoint_id = result_checkpoint_id
            thread.state_version += 1
            thread.status = RuntimeThreadStatus.STABLE.value
            thread.checkpoint_size_bytes = checkpoint_size_bytes
            row.status = RuntimeOverrideStatus.APPLIED.value
            row.after_state_version = thread.state_version
            row.completed_at = completed_at
            row.error_code = None
            row.error_summary = None
            attempt = self._latest_attempt(session, override_id)
            if attempt is not None:
                attempt.status = RuntimeOverrideStatus.APPLIED.value
                attempt.result_checkpoint_id = result_checkpoint_id
                attempt.completed_at = completed_at
            event_key = f"override:{override_id}:applied"
            existing_event = session.scalar(
                select(RuntimeThreadEvent).where(
                    RuntimeThreadEvent.thread_id == row.thread_id,
                    RuntimeThreadEvent.event_key == event_key,
                )
            )
            if existing_event is None:
                session.add(
                    RuntimeThreadEvent(
                        event_id=str(uuid4()),
                        event_key=event_key,
                        thread_id=row.thread_id,
                        event_type=RuntimeThreadEventType.RUNTIME_OVERRIDE_APPLIED.value,
                        checkpoint_id=result_checkpoint_id,
                        parent_checkpoint_id=row.source_checkpoint_id,
                        state_version=thread.state_version,
                        node=thread.current_node,
                        next_node=thread.next_node,
                        checkpoint_size_bytes=checkpoint_size_bytes,
                        worker_consumer=thread.worker_consumer,
                        metadata_json={
                            "override_id": override_id,
                            "operator_id": row.operator_id,
                            "entity_type": row.entity_type,
                            "entity_id": row.entity_id,
                            "field": row.field_name,
                            "old_value": row.old_value_json,
                            "new_value": row.new_value_json,
                            "reason": row.reason,
                        },
                    )
                )
            try:
                session.commit()
            except Exception as error:
                session.rollback()
                raise ThreadVersionConflict("Runtime override canonical promotion compare-and-swap failed.") from error
            return self._snapshot(row)

    def get(self, override_id: str) -> StoredRuntimeOverride | None:
        with self._session_factory() as session:
            row = session.scalar(select(RuntimeOverride).where(RuntimeOverride.override_id == override_id))
            return self._snapshot(row) if row is not None else None

    def list_by_thread(self, thread_id: str, *, limit: int) -> list[StoredRuntimeOverride]:
        bounded_limit = min(max(limit, 1), 100)
        with self._session_factory() as session:
            rows = session.scalars(
                select(RuntimeOverride)
                .where(RuntimeOverride.thread_id == thread_id)
                .order_by(RuntimeOverride.requested_at.desc(), RuntimeOverride.id.desc())
                .limit(bounded_limit)
            ).all()
            return [self._snapshot(row) for row in rows]

    @staticmethod
    def _required(session: Session, override_id: str) -> RuntimeOverride:
        row = session.scalar(select(RuntimeOverride).where(RuntimeOverride.override_id == override_id))
        if row is None:
            raise LookupError(override_id)
        return row

    @staticmethod
    def _latest_attempt(session: Session, override_id: str) -> RuntimeOverrideAttempt | None:
        return session.scalar(
            select(RuntimeOverrideAttempt)
            .where(RuntimeOverrideAttempt.override_id == override_id)
            .order_by(RuntimeOverrideAttempt.attempt_no.desc())
            .limit(1)
        )

    @staticmethod
    def _replay(
        row: RuntimeOverride,
        command: RuntimeOverrideCommand,
        fingerprint: str,
    ) -> StoredRuntimeOverride:
        if row.operator_id != command.operator_id or row.payload_fingerprint != fingerprint:
            raise RuntimeOverrideIdempotencyConflict("RUNTIME_OVERRIDE_IDEMPOTENCY_CONFLICT")
        return SqlAlchemyRuntimeOverrideRepository._snapshot(row, replayed=True)

    @staticmethod
    def _snapshot(row: RuntimeOverride, *, replayed: bool = False) -> StoredRuntimeOverride:
        return StoredRuntimeOverride(
            override_id=row.override_id,
            thread_id=row.thread_id,
            task_id=row.task_id,
            idempotency_key=row.idempotency_key,
            payload_fingerprint=row.payload_fingerprint,
            operator_id=row.operator_id,
            operator_role=row.operator_role,
            status=RuntimeOverrideStatus(row.status),
            decision=RuntimeOverrideDecision(row.decision) if row.decision else None,
            expected_version=row.expected_version,
            expected_next_node=row.expected_next_node,
            before_state_version=row.before_state_version,
            after_state_version=row.after_state_version,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            field=row.field_name,
            old_value=str(row.old_value_json),
            new_value=str(row.new_value_json),
            reason=row.reason,
            source_checkpoint_id=row.source_checkpoint_id,
            result_checkpoint_id=row.result_checkpoint_id,
            event_status=row.event_status,
            error_code=row.error_code,
            error_summary=row.error_summary,
            requested_at=row.requested_at,
            started_at=row.started_at,
            completed_at=row.completed_at,
            replayed=replayed,
        )
