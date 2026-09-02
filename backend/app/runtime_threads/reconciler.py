import json
from collections.abc import Sequence

from app.runtime_threads.models import (
    PromoteCheckpoint,
    RuntimeThreadEventType,
    RuntimeThreadSnapshot,
)
from app.runtime_threads.protocols import RuntimeCheckpointStore, RuntimeThreadRepository
from app.runtime_threads.runner import (
    RuntimeThreadCheckpointError,
    checkpoint_descends_from,
    checkpoint_has_initial_ancestry,
)


class ThreadCheckpointReconciler:
    def __init__(
        self,
        repository: RuntimeThreadRepository,
        checkpoint_store: RuntimeCheckpointStore,
        *,
        node_order: Sequence[str],
        scan_limit: int,
        max_checkpoint_bytes: int,
        worker_consumer: str,
    ) -> None:
        self._repository = repository
        self._checkpoint_store = checkpoint_store
        self._node_order = tuple(node_order)
        self._scan_limit = scan_limit
        self._max_checkpoint_bytes = max_checkpoint_bytes
        self._worker_consumer = worker_consumer

    async def reconcile(self, thread: RuntimeThreadSnapshot) -> RuntimeThreadSnapshot:
        if thread.terminal or thread.next_node is None:
            return thread
        records = await self._checkpoint_store.list_bounded(thread.thread_id, self._scan_limit)
        records_by_id = {record.checkpoint_id: record for record in records}
        direct_children = [
            record
            for record in records
            if record.thread_id == thread.thread_id
            and record.checkpoint_id != thread.current_checkpoint_id
            and (
                checkpoint_has_initial_ancestry(record, records_by_id)
                if thread.current_checkpoint_id is None
                else checkpoint_descends_from(record, thread.current_checkpoint_id, records_by_id)
            )
        ]
        candidates = [record for record in direct_children if self._is_continuous(thread, record)]
        if len(candidates) > 1:
            raise RuntimeThreadCheckpointError("DIVERGENT_ORPHAN_CHECKPOINTS")
        if not candidates:
            return thread
        candidate = candidates[0]
        if candidate.checkpoint_namespace != "":
            raise RuntimeThreadCheckpointError("CHECKPOINT_NAMESPACE_MISMATCH")
        try:
            json.dumps(candidate.state)
        except (TypeError, ValueError):
            raise RuntimeThreadCheckpointError("CHECKPOINT_STATE_NOT_JSON_SERIALIZABLE") from None
        if candidate.serialized_size_bytes > self._max_checkpoint_bytes:
            raise RuntimeThreadCheckpointError("CHECKPOINT_PAYLOAD_TOO_LARGE")
        node = str(candidate.state["last_completed_node"])
        command = PromoteCheckpoint(
            thread_id=thread.thread_id,
            expected_checkpoint_id=thread.current_checkpoint_id,
            expected_state_version=thread.state_version,
            checkpoint_id=candidate.checkpoint_id,
            parent_checkpoint_id=candidate.parent_checkpoint_id,
            node=node,
            next_node=self._next_node(node),
            checkpoint_size_bytes=candidate.serialized_size_bytes,
            worker_consumer=self._worker_consumer,
            event_key=f"reconcile:{candidate.checkpoint_id}",
            event_type=RuntimeThreadEventType.RECONCILIATION,
        )
        try:
            return self._repository.promote_checkpoint(command)
        except Exception:
            raise RuntimeThreadCheckpointError("CHECKPOINT_RECONCILIATION_CONFLICT") from None

    def _is_continuous(self, thread: RuntimeThreadSnapshot, record) -> bool:
        node = record.state.get("last_completed_node")
        count = record.state.get("completed_node_count")
        return (
            node == thread.next_node
            and node in self._node_order
            and count == thread.checkpoint_count + 1
        )

    def _next_node(self, node: str) -> str | None:
        index = self._node_order.index(node)
        if index + 1 == len(self._node_order):
            return None
        return self._node_order[index + 1]
