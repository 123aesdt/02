from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from time import perf_counter
from typing import Any

from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from app.observability.recorder import MetricsRecorder, NoOpMetricsRecorder
from app.runtime_threads.models import CheckpointRecord


class RuntimeCheckpointStoreError(Exception):
    """A credential-safe checkpoint store failure."""

    def __init__(self, code: str = "RUNTIME_CHECKPOINT_UNAVAILABLE") -> None:
        self.code = code
        super().__init__(code)


class RedisRuntimeCheckpointStore:
    def __init__(
        self,
        saver: Any,
        *,
        context: AbstractAsyncContextManager[Any] | None = None,
        metrics: MetricsRecorder | None = None,
    ) -> None:
        self.saver = saver
        self._context = context
        self._setup_complete = False
        self._closed = False
        self.metrics = metrics or NoOpMetricsRecorder()

    @classmethod
    def from_redis_client(
        cls,
        redis_client: Any,
        *,
        ttl_minutes: int,
        refresh_on_read: bool,
        namespace: str = "countyflow",
        metrics: MetricsRecorder | None = None,
    ) -> RedisRuntimeCheckpointStore:
        saver = AsyncRedisSaver(
            redis_client=redis_client,
            ttl={"default_ttl": ttl_minutes, "refresh_on_read": refresh_on_read},
            checkpoint_prefix=f"{namespace}:checkpoint",
            checkpoint_write_prefix=f"{namespace}:checkpoint_write",
        )
        return cls(saver, metrics=metrics)

    @property
    def native_checkpointer(self) -> Any:
        return self.saver

    @classmethod
    async def from_url(
        cls,
        url: str,
        *,
        ttl_minutes: int,
        refresh_on_read: bool,
        namespace: str = "countyflow",
        metrics: MetricsRecorder | None = None,
    ) -> RedisRuntimeCheckpointStore:
        context = AsyncRedisSaver.from_conn_string(
            url,
            ttl={"default_ttl": ttl_minutes, "refresh_on_read": refresh_on_read},
            checkpoint_prefix=f"{namespace}:checkpoint",
            checkpoint_write_prefix=f"{namespace}:checkpoint_write",
        )
        try:
            saver = await context.__aenter__()
        except Exception:
            raise RuntimeCheckpointStoreError() from None
        return cls(saver, context=context, metrics=metrics)

    async def setup(self) -> None:
        if self._setup_complete:
            return
        try:
            await self.saver.asetup()
        except Exception:
            raise RuntimeCheckpointStoreError() from None
        self._setup_complete = True

    async def get_exact(self, thread_id: str, checkpoint_id: str) -> CheckpointRecord | None:
        started = perf_counter()
        config = self._config(thread_id, checkpoint_id=checkpoint_id)
        try:
            checkpoint_tuple = await self.saver.aget_tuple(config)
        except Exception:
            self._record("read", "error", started)
            raise RuntimeCheckpointStoreError() from None
        self._record("read", "success", started)
        if checkpoint_tuple is None:
            return None
        actual_id = checkpoint_tuple.config["configurable"].get("checkpoint_id")
        if actual_id != checkpoint_id:
            return None
        return self._to_record(checkpoint_tuple)

    async def list_bounded(self, thread_id: str, limit: int) -> list[CheckpointRecord]:
        if limit <= 0:
            return []
        records: list[CheckpointRecord] = []
        started = perf_counter()
        try:
            async for checkpoint_tuple in self.saver.alist(self._config(thread_id), limit=limit):
                records.append(self._to_record(checkpoint_tuple))
        except Exception:
            self._record("read", "error", started)
            raise RuntimeCheckpointStoreError() from None
        self._record("read", "success", started)
        return records

    def _record(self, operation: str, result: str, started: float) -> None:
        self.metrics.increment("countyflow_checkpoint_operations_total", {"operation": operation, "result": result})
        self.metrics.observe("countyflow_checkpoint_duration_seconds", perf_counter() - started, {"operation": operation})

    def serialized_size(self, checkpoint: object) -> int:
        encoding, payload = self.saver.serde.dumps_typed(checkpoint)
        encoding_bytes = encoding if isinstance(encoding, bytes) else encoding.encode()
        return len(encoding_bytes) + len(payload)

    async def delete_thread(self, thread_id: str) -> None:
        try:
            await self.saver.adelete_thread(thread_id)
        except Exception:
            raise RuntimeCheckpointStoreError() from None

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._context is not None:
            try:
                await self._context.__aexit__(None, None, None)
            except Exception:
                raise RuntimeCheckpointStoreError() from None

    @staticmethod
    def _config(thread_id: str, *, checkpoint_id: str | None = None) -> dict[str, Any]:
        configurable: dict[str, Any] = {"thread_id": thread_id, "checkpoint_ns": ""}
        if checkpoint_id is not None:
            configurable["checkpoint_id"] = checkpoint_id
        return {"configurable": configurable}

    def _to_record(self, checkpoint_tuple: Any) -> CheckpointRecord:
        configurable = checkpoint_tuple.config["configurable"]
        checkpoint = checkpoint_tuple.checkpoint
        parent_config = checkpoint_tuple.parent_config
        parent_id = None
        if parent_config is not None:
            parent_id = parent_config["configurable"].get("checkpoint_id")
        return CheckpointRecord(
            thread_id=str(configurable["thread_id"]),
            checkpoint_id=str(configurable.get("checkpoint_id") or checkpoint["id"]),
            parent_checkpoint_id=parent_id,
            checkpoint_namespace=str(configurable.get("checkpoint_ns", "")),
            state=dict(checkpoint.get("channel_values", {})),
            metadata=dict(checkpoint_tuple.metadata),
            config={
                "configurable": {
                    "thread_id": str(configurable["thread_id"]),
                    "checkpoint_ns": str(configurable.get("checkpoint_ns", "")),
                    "checkpoint_id": str(configurable.get("checkpoint_id") or checkpoint["id"]),
                }
            },
            serialized_size_bytes=self.serialized_size(checkpoint),
        )
