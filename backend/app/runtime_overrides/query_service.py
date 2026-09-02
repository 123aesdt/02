from datetime import UTC, datetime

from app.runtime_overrides.query_models import (
    RuntimeInterventionContext,
    RuntimeInterventionEligibility,
    RuntimeInterventionTarget,
)
from app.runtime_threads.checkpoint_store import RuntimeCheckpointStoreError
from app.runtime_threads.models import RuntimeThreadStatus
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission

ALLOWED_NEW_VALUES = ("BROKEN", "UNAVAILABLE", "MAINTENANCE")


class RuntimeOverrideQueryError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class RuntimeOverrideQueryService:
    def __init__(
        self,
        override_repository,
        thread_repository,
        checkpoint_store,
        *,
        clock=None,
    ) -> None:
        self._overrides = override_repository
        self._threads = thread_repository
        self._store = checkpoint_store
        self._clock = clock or (lambda: datetime.now(UTC))

    async def get_intervention_context(
        self, thread_id: str, principal: AuthenticatedPrincipal
    ) -> RuntimeInterventionContext:
        self._require_read(principal)
        thread = self._threads.get_by_thread_id(thread_id)
        if thread is None:
            raise RuntimeOverrideQueryError("THREAD_NOT_FOUND")

        can_override = principal.can(Permission.RUNTIME_OVERRIDE)
        record = None
        if thread.current_checkpoint_id is not None:
            try:
                record = await self._store.get_exact(thread.thread_id, thread.current_checkpoint_id)
            except RuntimeCheckpointStoreError:
                raise RuntimeOverrideQueryError("CHECKPOINT_STORE_UNAVAILABLE") from None

        state = record.state if record is not None else {}
        target = self._target(state)
        eligibility, reason = self._eligibility(thread, can_override, record is not None, target)
        return RuntimeInterventionContext(
            thread_id=thread.thread_id,
            task_id=thread.task_id,
            runtime_status=thread.status.value,
            state_version=thread.state_version,
            current_node=thread.current_node,
            next_node=thread.next_node,
            canonical_checkpoint_id=thread.current_checkpoint_id,
            checkpoint_available=record is not None,
            eligibility=eligibility,
            eligibility_reason_code=reason,
            can_override=can_override,
            target=target,
            observed_at=self._clock(),
        )

    def get(self, override_id: str, principal: AuthenticatedPrincipal):
        self._require_read(principal)
        item = self._overrides.get(override_id)
        if item is None:
            raise RuntimeOverrideQueryError("RUNTIME_OVERRIDE_NOT_FOUND")
        return item

    def list_by_thread(self, thread_id: str, principal: AuthenticatedPrincipal, *, limit: int):
        self._require_read(principal)
        thread = self._threads.get_by_thread_id(thread_id)
        if thread is None:
            raise RuntimeOverrideQueryError("THREAD_NOT_FOUND")
        return self._overrides.list_by_thread(thread.thread_id, limit=min(max(limit, 1), 100))

    @staticmethod
    def _require_read(principal: AuthenticatedPrincipal) -> None:
        if not principal.can(Permission.RUNTIME_READ):
            raise RuntimeOverrideQueryError("RUNTIME_THREAD_FORBIDDEN") from None

    @staticmethod
    def _target(state: dict[str, object]) -> RuntimeInterventionTarget | None:
        entity_id = state.get("vehicle_id")
        current_value = state.get("vehicle_status")
        if not isinstance(entity_id, str) or not isinstance(current_value, str):
            return None
        display_name = state.get("vehicle_display_name")
        return RuntimeInterventionTarget(
            entity_type="Vehicle",
            entity_id=entity_id,
            display_name=display_name if isinstance(display_name, str) and display_name else entity_id,
            field="status",
            current_value=current_value,
            allowed_new_values=ALLOWED_NEW_VALUES if current_value == "NORMAL" else (),
        )

    @staticmethod
    def _eligibility(thread, can_override: bool, checkpoint_available: bool, target):
        if not can_override:
            return RuntimeInterventionEligibility.NO_PERMISSION, "RUNTIME_OVERRIDE_FORBIDDEN"
        if thread.status is RuntimeThreadStatus.TERMINAL:
            return RuntimeInterventionEligibility.TERMINAL, "THREAD_TERMINAL"
        if thread.status is RuntimeThreadStatus.OVERRIDING:
            return RuntimeInterventionEligibility.BUSY, "RUNTIME_OVERRIDE_BUSY"
        if thread.status is not RuntimeThreadStatus.STABLE:
            return RuntimeInterventionEligibility.NOT_STABLE, "THREAD_NOT_STABLE"
        if (thread.current_node, thread.next_node) != ("environment", "capacity"):
            return RuntimeInterventionEligibility.WRONG_BOUNDARY, "RUNTIME_OVERRIDE_WRONG_BOUNDARY"
        if not checkpoint_available:
            return RuntimeInterventionEligibility.WRONG_BOUNDARY, "CANONICAL_CHECKPOINT_MISSING"
        if target is None:
            return RuntimeInterventionEligibility.WRONG_BOUNDARY, "RUNTIME_STATE_PRECONDITION_FAILED"
        if target.current_value != "NORMAL":
            return RuntimeInterventionEligibility.WRONG_BOUNDARY, "OVERRIDE_VALUE_INVALID"
        return RuntimeInterventionEligibility.ELIGIBLE, None
