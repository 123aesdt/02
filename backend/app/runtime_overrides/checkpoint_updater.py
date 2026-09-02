import json
from collections.abc import Mapping

from app.runtime_overrides.models import UpdatedCheckpoint
from app.runtime_threads.models import CheckpointRecord


class LangGraphStateUpdater:
    def __init__(self, graph, checkpoint_store, *, max_checkpoint_bytes: int) -> None:
        self._graph = graph
        self._checkpoint_store = checkpoint_store
        self._max_checkpoint_bytes = max_checkpoint_bytes

    async def update(
        self,
        source: CheckpointRecord,
        patch: Mapping[str, object],
        *,
        as_node: str,
        expected_next_node: str,
        override_id: str,
    ) -> UpdatedCheckpoint:
        if set(patch) != {"vehicle_status"}:
            raise ValueError("STATE_DIFF_NOT_ALLOWED")
        result_config = await self._graph.aupdate_state(
            source.config,
            dict(patch),
            as_node=as_node,
            task_id=override_id,
        )
        configurable = result_config.get("configurable", {})
        checkpoint_id = configurable.get("checkpoint_id")
        if not isinstance(checkpoint_id, str) or not checkpoint_id:
            raise ValueError("RESULT_CHECKPOINT_ID_MISSING")
        record = await self._checkpoint_store.get_exact(source.thread_id, checkpoint_id)
        if record is None:
            raise ValueError("RESULT_CHECKPOINT_MISSING")
        snapshot = await self._graph.aget_state(result_config)
        next_nodes = tuple(str(node) for node in snapshot.next)
        self._validate(source, record, next_nodes, dict(patch), expected_next_node)
        return UpdatedCheckpoint(record=record, next_nodes=next_nodes)

    def _validate(
        self,
        source: CheckpointRecord,
        result: CheckpointRecord,
        next_nodes: tuple[str, ...],
        patch: dict[str, object],
        expected_next_node: str,
    ) -> None:
        if result.thread_id != source.thread_id:
            raise ValueError("CHECKPOINT_THREAD_MISMATCH")
        if result.checkpoint_namespace != source.checkpoint_namespace or result.checkpoint_namespace != "":
            raise ValueError("CHECKPOINT_NAMESPACE_MISMATCH")
        if result.parent_checkpoint_id != source.checkpoint_id:
            raise ValueError("CHECKPOINT_ANCESTRY_MISMATCH")
        if next_nodes != (expected_next_node,):
            raise ValueError("RUNTIME_NEXT_NODE_CONFLICT")
        if result.state.get("last_completed_node") != source.state.get("last_completed_node"):
            raise ValueError("CHECKPOINT_NODE_MISMATCH")
        if result.state.get("completed_node_count") != source.state.get("completed_node_count"):
            raise ValueError("CHECKPOINT_COUNT_MISMATCH")
        changed = {
            key
            for key in set(source.state) | set(result.state)
            if source.state.get(key) != result.state.get(key)
        }
        if changed != set(patch):
            raise ValueError("STATE_DIFF_NOT_ALLOWED")
        if any(result.state.get(key) != value for key, value in patch.items()):
            raise ValueError("STATE_DIFF_NOT_ALLOWED")
        try:
            json.dumps(result.state)
        except (TypeError, ValueError):
            raise ValueError("CHECKPOINT_STATE_NOT_JSON_SERIALIZABLE") from None
        if result.serialized_size_bytes > self._max_checkpoint_bytes:
            raise ValueError("CHECKPOINT_PAYLOAD_TOO_LARGE")
