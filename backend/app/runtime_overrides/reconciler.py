import json
from datetime import UTC, datetime

from app.runtime_overrides.models import RuntimeOverrideDecision, RuntimeOverrideStatus
from app.runtime_threads.models import RuntimeThreadStatus, ThreadVersionConflict


class RuntimeOverrideReconciler:
    """Promotes only the exact candidate recorded in the durable override ledger."""

    def __init__(self, repository, thread_repository, checkpoint_store, *, max_checkpoint_bytes: int, clock=None) -> None:
        self._repository = repository
        self._threads = thread_repository
        self._store = checkpoint_store
        self._max_bytes = max_checkpoint_bytes
        self._clock = clock or (lambda: datetime.now(UTC))

    async def reconcile(self, override_id: str):
        item = self._repository.get(override_id)
        if item is None:
            raise LookupError(override_id)
        if item.status is RuntimeOverrideStatus.APPLIED:
            return item
        if item.status is not RuntimeOverrideStatus.PARTIAL:
            return item
        thread = self._threads.get_by_thread_id(item.thread_id)
        if (
            thread is None
            or thread.status is not RuntimeThreadStatus.OVERRIDING
            or thread.current_checkpoint_id != item.source_checkpoint_id
            or thread.state_version != item.expected_version
        ):
            return self._repository.finish(
                override_id,
                status=RuntimeOverrideStatus.CONFLICT,
                decision=RuntimeOverrideDecision.NEEDS_DIFFERENT_BOUNDARY,
                error_code="RUNTIME_STATE_VERSION_CONFLICT",
                completed_at=self._clock(),
            )
        if item.source_checkpoint_id is None or item.result_checkpoint_id is None:
            return self._invalid(override_id, "RUNTIME_OVERRIDE_RESULT_MISSING")
        source = await self._store.get_exact(item.thread_id, item.source_checkpoint_id)
        result = await self._store.get_exact(item.thread_id, item.result_checkpoint_id)
        if source is None or result is None:
            return self._invalid(override_id, "RUNTIME_OVERRIDE_RESULT_MISSING")
        if not self._valid(item, source, result):
            return self._invalid(override_id, "RUNTIME_OVERRIDE_RESULT_INVALID")
        try:
            return self._repository.promote_applied(
                override_id,
                result_checkpoint_id=result.checkpoint_id,
                checkpoint_size_bytes=result.serialized_size_bytes,
                completed_at=self._clock(),
            )
        except ThreadVersionConflict:
            return self._repository.finish(
                override_id,
                status=RuntimeOverrideStatus.CONFLICT,
                decision=RuntimeOverrideDecision.NEEDS_DIFFERENT_BOUNDARY,
                error_code="RUNTIME_STATE_VERSION_CONFLICT",
                completed_at=self._clock(),
            )

    def _invalid(self, override_id: str, code: str):
        return self._repository.mark_partial(override_id, error_code=code, completed_at=self._clock())

    def _valid(self, item, source, result) -> bool:
        if (
            result.thread_id != source.thread_id
            or result.checkpoint_namespace != source.checkpoint_namespace
            or result.checkpoint_namespace != ""
            or result.parent_checkpoint_id != source.checkpoint_id
            or result.serialized_size_bytes > self._max_bytes
            or source.state.get("vehicle_id") != item.entity_id
            or source.state.get("vehicle_status") != item.old_value
            or result.state.get("vehicle_status") != item.new_value
            or result.state.get("last_completed_node") != source.state.get("last_completed_node")
            or result.state.get("completed_node_count") != source.state.get("completed_node_count")
        ):
            return False
        changed = {
            key
            for key in set(source.state) | set(result.state)
            if source.state.get(key) != result.state.get(key)
        }
        if changed != {"vehicle_status"}:
            return False
        try:
            json.dumps(result.state)
        except (TypeError, ValueError):
            return False
        return True
