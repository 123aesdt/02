import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.observability.recorder import MetricsRecorder, NoOpMetricsRecorder
from app.runtime_overrides.identity import payload_fingerprint
from app.runtime_overrides.models import (
    RuntimeOverrideCommand,
    RuntimeOverrideDecision,
    RuntimeOverrideRequest,
    RuntimeOverrideStatus,
    StoredRuntimeOverride,
)
from app.runtime_threads.checkpoint_store import RuntimeCheckpointStoreError
from app.runtime_threads.models import BoundaryClaimConflict, RuntimeThreadStatus, ThreadVersionConflict
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission


class RuntimeOverrideService:
    def __init__(
        self,
        repository,
        thread_repository,
        checkpoint_store,
        state_updater,
        policy,
        lock,
        *,
        event_publisher=None,
        clock=None,
        intent_ttl: timedelta = timedelta(seconds=30),
        metrics: MetricsRecorder | None = None,
    ) -> None:
        self._repository = repository
        self._threads = thread_repository
        self._store = checkpoint_store
        self._updater = state_updater
        self._policy = policy
        self._lock = lock
        self._events = event_publisher
        self._clock = clock or (lambda: datetime.now(UTC))
        self._intent_ttl = intent_ttl
        self.metrics = metrics or NoOpMetricsRecorder()

    async def apply(
        self,
        thread_id: str,
        request: RuntimeOverrideRequest,
        principal: AuthenticatedPrincipal,
    ) -> StoredRuntimeOverride:
        started = time.perf_counter()
        try:
            result = await self._apply(thread_id, request, principal)
        finally:
            self.metrics.observe("countyflow_runtime_override_duration_seconds", time.perf_counter() - started)
        if result.status.value in {"APPLIED", "REJECTED", "CONFLICT", "PARTIAL", "FAILED"}:
            self.metrics.increment("countyflow_runtime_overrides_total", {"result": result.status.value})
        if result.status is RuntimeOverrideStatus.CONFLICT:
            reason = {
                "RUNTIME_STATE_VERSION_CONFLICT": "version",
                "RUNTIME_OVERRIDE_BUSY": "busy",
                "THREAD_NOT_STABLE": "not_stable",
                "THREAD_TERMINAL": "terminal",
                "RUNTIME_OVERRIDE_FORBIDDEN": "permission",
            }.get(result.error_code or "", "precondition")
            self.metrics.increment("countyflow_runtime_override_conflicts_total", {"reason_code": reason})
        return result

    async def _apply(
        self,
        thread_id: str,
        request: RuntimeOverrideRequest,
        principal: AuthenticatedPrincipal,
    ) -> StoredRuntimeOverride:
        operation_started = time.perf_counter()
        authorization_started = time.perf_counter()
        authorization_ms = lock_ms = checkpoint_read_ms = state_update_ms = promotion_ms = 0.0
        override_id: str | None = None
        thread = self._threads.get_by_thread_id(thread_id)
        if thread is None:
            raise RuntimeOverrideServiceError("THREAD_NOT_FOUND")
        if not principal.can(Permission.RUNTIME_OVERRIDE):
            raise RuntimeOverrideServiceError("RUNTIME_OVERRIDE_FORBIDDEN")
        authorization_ms = (time.perf_counter() - authorization_started) * 1000

        now = self._clock()
        command = RuntimeOverrideCommand(
            override_id=str(uuid4()),
            idempotency_key=request.idempotency_key,
            thread_id=thread_id,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            field=request.field,
            old_value=request.old_value,
            new_value=request.new_value,
            reason=request.reason,
            expected_version=request.expected_version,
            expected_next_node=request.expected_next_node,
            operator_id=principal.subject_id,
            operator_role=sorted(role.value for role in principal.roles)[0],
            operator_permissions=frozenset(permission.value for permission in principal.permissions),
            requested_at=now,
        )
        stored = self._repository.begin_or_replay(
            command,
            payload_fingerprint(command),
            intent_expires_at=now + self._intent_ttl,
        )
        override_id = stored.override_id
        if stored.replayed and stored.status is not RuntimeOverrideStatus.PENDING:
            if stored.status is RuntimeOverrideStatus.APPLYING:
                if stored.result_checkpoint_id is not None:
                    return self._repository.mark_partial(
                        stored.override_id,
                        error_code="RUNTIME_OVERRIDE_RECONCILIATION_REQUIRED",
                        completed_at=self._clock(),
                    )
                current = self._threads.get_by_thread_id(thread_id)
                if (
                    current is not None
                    and current.status is RuntimeThreadStatus.OVERRIDING
                    and current.current_checkpoint_id == stored.source_checkpoint_id
                    and current.state_version == stored.expected_version
                    and current.next_node == stored.expected_next_node
                ):
                    try:
                        self._threads.release_override_boundary(
                            thread_id,
                            expected_checkpoint_id=stored.source_checkpoint_id or "",
                            expected_state_version=stored.expected_version,
                            expected_next_node=stored.expected_next_node or "",
                        )
                    except BoundaryClaimConflict:
                        pass
                return self._repository.finish(
                    stored.override_id,
                    status=RuntimeOverrideStatus.FAILED,
                    decision=RuntimeOverrideDecision.REJECTED,
                    error_code="RUNTIME_OVERRIDE_INTERRUPTED",
                    completed_at=self._clock(),
                )
            return stored
        if self._events is not None and hasattr(self._events, "publish_requested"):
            try:
                await self._events.publish_requested(stored)
            except Exception:
                pass

        lock_started = time.perf_counter()
        handle = await self._lock.acquire(thread_id)
        lock_ms = (time.perf_counter() - lock_started) * 1000
        if not handle.acquired:
            return self._repository.finish(
                stored.override_id,
                status=RuntimeOverrideStatus.CONFLICT,
                decision=RuntimeOverrideDecision.NEEDS_DIFFERENT_BOUNDARY,
                error_code="RUNTIME_OVERRIDE_BUSY",
                completed_at=self._clock(),
            )
        claimed = False
        candidate_created = False
        try:
            thread = self._threads.get_by_thread_id(thread_id)
            if thread is None:
                return self._finish(stored.override_id, "THREAD_NOT_FOUND", rejected=True)
            if thread.status is RuntimeThreadStatus.TERMINAL:
                return self._finish(stored.override_id, "THREAD_TERMINAL", rejected=True)
            if thread.status is not RuntimeThreadStatus.STABLE:
                return self._finish(stored.override_id, "THREAD_NOT_STABLE")
            if thread.state_version != request.expected_version:
                return self._finish(stored.override_id, "RUNTIME_STATE_VERSION_CONFLICT")
            if thread.current_checkpoint_id is None:
                return self._finish(stored.override_id, "CANONICAL_CHECKPOINT_MISSING", rejected=True)
            try:
                checkpoint_read_started = time.perf_counter()
                source = await self._store.get_exact(thread_id, thread.current_checkpoint_id)
                checkpoint_read_ms = (time.perf_counter() - checkpoint_read_started) * 1000
            except RuntimeCheckpointStoreError:
                return self._finish(stored.override_id, "CHECKPOINT_STORE_UNAVAILABLE", failed=True)
            if source is None:
                return self._finish(stored.override_id, "CANONICAL_CHECKPOINT_MISSING", failed=True)
            policy = self._policy.evaluate(command, thread, source.state)
            if not policy.allowed:
                return self._repository.finish(
                    stored.override_id,
                    status=(
                        RuntimeOverrideStatus.REJECTED
                        if policy.decision is RuntimeOverrideDecision.REJECTED
                        else RuntimeOverrideStatus.CONFLICT
                    ),
                    decision=policy.decision,
                    error_code=policy.error_code or "RUNTIME_STATE_PRECONDITION_FAILED",
                    completed_at=self._clock(),
                )
            try:
                self._threads.claim_override_boundary(
                    thread_id,
                    expected_checkpoint_id=source.checkpoint_id,
                    expected_state_version=thread.state_version,
                    expected_next_node=thread.next_node or "",
                )
            except BoundaryClaimConflict:
                return self._finish(stored.override_id, "THREAD_NOT_STABLE")
            claimed = True
            self._repository.mark_applying(
                stored.override_id,
                before_state_version=thread.state_version,
                source_checkpoint_id=source.checkpoint_id,
                started_at=self._clock(),
            )
            try:
                state_update_started = time.perf_counter()
                updated = await self._updater.update(
                    source,
                    {"vehicle_status": request.new_value},
                    as_node="environment",
                    expected_next_node=thread.next_node or "",
                    override_id=stored.override_id,
                )
                state_update_ms = (time.perf_counter() - state_update_started) * 1000
            except (RuntimeCheckpointStoreError, ValueError):
                self._threads.release_override_boundary(
                    thread_id,
                    expected_checkpoint_id=source.checkpoint_id,
                    expected_state_version=thread.state_version,
                    expected_next_node=thread.next_node or "",
                )
                claimed = False
                return self._finish(stored.override_id, "CHECKPOINT_UPDATE_FAILED", failed=True)
            candidate_created = True
            self._repository.attach_result_checkpoint(stored.override_id, updated.record.checkpoint_id)
            try:
                promotion_started = time.perf_counter()
                applied = self._repository.promote_applied(
                    stored.override_id,
                    result_checkpoint_id=updated.record.checkpoint_id,
                    checkpoint_size_bytes=updated.record.serialized_size_bytes,
                    completed_at=self._clock(),
                )
                promotion_ms = (time.perf_counter() - promotion_started) * 1000
            except ThreadVersionConflict:
                return self._repository.mark_partial(
                    stored.override_id,
                    error_code="CHECKPOINT_PROMOTION_CONFLICT",
                    completed_at=self._clock(),
                )
            claimed = False
            if self._events is not None:
                try:
                    await self._events.publish_applied(applied)
                except Exception:
                    return self._repository.mark_event_status(applied.override_id, "FAILED")
            return self._repository.mark_event_status(applied.override_id, "PUBLISHED")
        finally:
            await self._lock.release(handle)
            # A known orphan remains fenced in OVERRIDING for exact reconciliation.
            if claimed and not candidate_created:
                current = self._threads.get_by_thread_id(thread_id)
                if current is not None and current.status is RuntimeThreadStatus.OVERRIDING:
                    self._threads.release_override_boundary(
                        thread_id,
                        expected_checkpoint_id=current.current_checkpoint_id or "",
                        expected_state_version=current.state_version,
                        expected_next_node=current.next_node or "",
                    )
            if override_id is not None and hasattr(self._repository, "record_timings"):
                self._repository.record_timings(
                    override_id,
                    authorization_ms=authorization_ms,
                    lock_ms=lock_ms,
                    checkpoint_read_ms=checkpoint_read_ms,
                    state_update_ms=state_update_ms,
                    promotion_ms=promotion_ms,
                    total_ms=(time.perf_counter() - operation_started) * 1000,
                )

    def get(self, override_id: str) -> StoredRuntimeOverride:
        item = self._repository.get(override_id)
        if item is None:
            raise RuntimeOverrideServiceError("RUNTIME_OVERRIDE_NOT_FOUND")
        return item

    def _finish(
        self,
        override_id: str,
        code: str,
        *,
        rejected: bool = False,
        failed: bool = False,
    ) -> StoredRuntimeOverride:
        status = RuntimeOverrideStatus.FAILED if failed else (
            RuntimeOverrideStatus.REJECTED if rejected else RuntimeOverrideStatus.CONFLICT
        )
        decision = RuntimeOverrideDecision.REJECTED if rejected or failed else RuntimeOverrideDecision.NEEDS_DIFFERENT_BOUNDARY
        return self._repository.finish(
            override_id,
            status=status,
            decision=decision,
            error_code=code,
            completed_at=self._clock(),
        )


class RuntimeOverrideServiceError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
