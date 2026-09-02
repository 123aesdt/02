from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from inspect import isawaitable
from typing import Any

from app.observability.recorder import MetricsRecorder, NoOpMetricsRecorder
from app.runtime_threads.models import (
    CheckpointPayloadTooLarge,
    CheckpointRecord,
    PromoteCheckpoint,
    RuntimeThreadSnapshot,
    ThreadVersionConflict,
)
from app.runtime_threads.protocols import RuntimeCheckpointStore, RuntimeThreadRepository


def checkpoint_descends_from(
    record: CheckpointRecord,
    checkpoint_id: str,
    records_by_id: Mapping[str, CheckpointRecord],
) -> bool:
    parent_id = record.parent_checkpoint_id
    seen: set[str] = set()
    while parent_id is not None and parent_id not in seen:
        if parent_id == checkpoint_id:
            return True
        seen.add(parent_id)
        parent = records_by_id.get(parent_id)
        if parent is None:
            return False
        parent_id = parent.parent_checkpoint_id
    return False


def checkpoint_has_initial_ancestry(
    record: CheckpointRecord,
    records_by_id: Mapping[str, CheckpointRecord],
) -> bool:
    parent_id = record.parent_checkpoint_id
    seen: set[str] = set()
    while parent_id is not None and parent_id not in seen:
        seen.add(parent_id)
        parent = records_by_id.get(parent_id)
        if parent is None or parent.thread_id != record.thread_id or parent.checkpoint_namespace != "":
            return False
        if parent.state.get("completed_node_count") not in (None, 0):
            return False
        parent_id = parent.parent_checkpoint_id
    return parent_id is None


class RuntimeThreadCheckpointError(Exception):
    """A retryable checkpoint boundary failure with a safe public code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class CheckpointedGraphRunner:
    def __init__(
        self,
        graph: Any,
        repository: RuntimeThreadRepository,
        checkpoint_store: RuntimeCheckpointStore,
        *,
        node_order: Sequence[str],
        max_checkpoint_bytes: int,
        worker_consumer: str,
        event_publisher: Any | None = None,
        metrics: MetricsRecorder | None = None,
    ) -> None:
        self._graph = graph
        self._repository = repository
        self._checkpoint_store = checkpoint_store
        self._node_order = tuple(node_order)
        self._max_checkpoint_bytes = max_checkpoint_bytes
        self._worker_consumer = worker_consumer
        self._event_publisher = event_publisher
        self._metrics = metrics or NoOpMetricsRecorder()

    async def setup(self) -> None:
        await self._checkpoint_store.setup()

    async def close(self) -> None:
        await self._checkpoint_store.close()

    async def publish_terminal(self, thread: RuntimeThreadSnapshot) -> None:
        if self._event_publisher is None or not hasattr(self._event_publisher, "publish_terminal"):
            return
        try:
            await self._event_publisher.publish_terminal(thread)
        except Exception:
            return

    async def run_new(
        self,
        thread: RuntimeThreadSnapshot,
        state: Mapping[str, object],
    ) -> Mapping[str, object]:
        return await self._run(thread, dict(state), checkpoint_id=None, mark_resume=False)

    async def resume(
        self,
        thread: RuntimeThreadSnapshot,
        *,
        resume_key: str | None = None,
    ) -> Mapping[str, object]:
        if thread.terminal:
            raise RuntimeThreadCheckpointError("RUNTIME_THREAD_TERMINAL")
        if thread.current_checkpoint_id is None:
            raise RuntimeThreadCheckpointError("CANONICAL_CHECKPOINT_MISSING")
        return await self._run(
            thread,
            None,
            checkpoint_id=thread.current_checkpoint_id,
            mark_resume=True,
            resume_key=resume_key,
        )

    async def _run(
        self,
        thread: RuntimeThreadSnapshot,
        graph_input: Mapping[str, object] | None,
        *,
        checkpoint_id: str | None,
        mark_resume: bool,
        resume_key: str | None = None,
    ) -> Mapping[str, object]:
        config = self._config(thread.thread_id, checkpoint_id)
        current = thread
        result: dict[str, object] = dict(graph_input or {})
        try:
            await self._start_events(thread)
            stream = self._graph.astream(
                graph_input,
                config=config,
                stream_mode="updates",
                durability="sync",
            )
            async for update in stream:
                if mark_resume:
                    current = self._repository.mark_resumed(
                        current.thread_id,
                        f"resume:{checkpoint_id}:{resume_key or self._worker_consumer}",
                        self._worker_consumer,
                    )
                    await self._publish_resumed(current)
                    mark_resume = False
                if not isinstance(update, Mapping):
                    continue
                for node, patch in update.items():
                    if node not in self._node_order or not isinstance(patch, Mapping):
                        continue
                    result.update(patch)
                    record = await self._latest_boundary(current, node)
                    current = await self._promote(current, record, node)
                    await self._publish(current, node, patch, record.state)
        except RuntimeThreadCheckpointError:
            raise
        except CheckpointPayloadTooLarge:
            raise RuntimeThreadCheckpointError("CHECKPOINT_PAYLOAD_TOO_LARGE") from None
        except ThreadVersionConflict:
            raise RuntimeThreadCheckpointError("CHECKPOINT_PROMOTION_CONFLICT") from None
        except Exception:
            raise RuntimeThreadCheckpointError("CHECKPOINT_RUNTIME_FAILURE") from None
        return result

    async def _latest_boundary(self, thread: RuntimeThreadSnapshot, node: str) -> CheckpointRecord:
        records = await self._checkpoint_store.list_bounded(thread.thread_id, 10)
        records_by_id = {record.checkpoint_id: record for record in records}
        for record in records:
            parent_is_continuous = (
                checkpoint_has_initial_ancestry(record, records_by_id)
                if thread.current_checkpoint_id is None
                else checkpoint_descends_from(record, thread.current_checkpoint_id, records_by_id)
            )
            if (
                record.thread_id == thread.thread_id
                and record.state.get("last_completed_node") == node
                and record.state.get("completed_node_count") == thread.checkpoint_count + 1
                and node == thread.next_node
                and parent_is_continuous
            ):
                return record
        raise RuntimeThreadCheckpointError("CHECKPOINT_BOUNDARY_MISSING")

    async def _promote(
        self,
        thread: RuntimeThreadSnapshot,
        record: CheckpointRecord,
        node: str,
    ) -> RuntimeThreadSnapshot:
        if record.checkpoint_namespace != "":
            raise RuntimeThreadCheckpointError("CHECKPOINT_NAMESPACE_MISMATCH")
        try:
            json.dumps(record.state)
        except (TypeError, ValueError):
            raise RuntimeThreadCheckpointError("CHECKPOINT_STATE_NOT_JSON_SERIALIZABLE") from None
        if record.serialized_size_bytes > self._max_checkpoint_bytes:
            raise CheckpointPayloadTooLarge
        self._metrics.observe("countyflow_checkpoint_payload_bytes", record.serialized_size_bytes)
        next_node = self._next_node(node)
        command = PromoteCheckpoint(
            thread_id=thread.thread_id,
            expected_checkpoint_id=thread.current_checkpoint_id,
            expected_state_version=thread.state_version,
            checkpoint_id=record.checkpoint_id,
            parent_checkpoint_id=record.parent_checkpoint_id,
            node=node,
            next_node=next_node,
            checkpoint_size_bytes=record.serialized_size_bytes,
            worker_consumer=self._worker_consumer,
            event_key=f"checkpoint:{record.checkpoint_id}",
        )
        try:
            promoted = self._repository.promote_checkpoint(command)
        except ThreadVersionConflict:
            self._metrics.increment("countyflow_checkpoint_operations_total", {"operation": "promote", "result": "conflict"})
            raise
        self._metrics.increment("countyflow_checkpoint_operations_total", {"operation": "promote", "result": "success"})
        return promoted

    async def _publish(
        self,
        thread: RuntimeThreadSnapshot,
        node: str,
        patch: Mapping[str, object],
        state: Mapping[str, object],
    ) -> None:
        if self._event_publisher is None:
            return
        try:
            result = self._event_publisher(thread, node, patch, state)
            if isawaitable(result):
                await result
        except Exception:
            return

    async def _start_events(self, thread: RuntimeThreadSnapshot) -> None:
        if self._event_publisher is None or not hasattr(self._event_publisher, "start"):
            return
        try:
            await self._event_publisher.start(thread)
        except Exception:
            return

    async def _publish_resumed(self, thread: RuntimeThreadSnapshot) -> None:
        if self._event_publisher is None or not hasattr(self._event_publisher, "publish_resumed"):
            return
        try:
            await self._event_publisher.publish_resumed(thread)
        except Exception:
            return

    def _next_node(self, node: str) -> str | None:
        index = self._node_order.index(node)
        if index + 1 == len(self._node_order):
            return None
        return self._node_order[index + 1]

    @staticmethod
    def _config(thread_id: str, checkpoint_id: str | None) -> dict[str, Any]:
        configurable: dict[str, Any] = {"thread_id": thread_id, "checkpoint_ns": ""}
        if checkpoint_id is not None:
            configurable["checkpoint_id"] = checkpoint_id
        return {"configurable": configurable}
