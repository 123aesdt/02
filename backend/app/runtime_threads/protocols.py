from collections.abc import Sequence
from typing import Protocol

from app.runtime_threads.models import CheckpointRecord, PromoteCheckpoint, RuntimeThreadEventSnapshot, RuntimeThreadSnapshot


class RuntimeThreadRepository(Protocol):
    def create_for_task(self, task_id: str, thread_id: str) -> RuntimeThreadSnapshot: ...

    def get_by_thread_id(self, thread_id: str) -> RuntimeThreadSnapshot | None: ...

    def get_by_task_id(self, task_id: str) -> RuntimeThreadSnapshot | None: ...

    def claim_override_boundary(
        self,
        thread_id: str,
        *,
        expected_checkpoint_id: str,
        expected_state_version: int,
        expected_next_node: str,
    ) -> RuntimeThreadSnapshot: ...

    def claim_next_node(
        self,
        thread_id: str,
        *,
        expected_checkpoint_id: str,
        expected_state_version: int,
        expected_next_node: str,
        worker_consumer: str,
    ) -> RuntimeThreadSnapshot: ...

    def release_override_boundary(
        self,
        thread_id: str,
        *,
        expected_checkpoint_id: str,
        expected_state_version: int,
        expected_next_node: str,
    ) -> RuntimeThreadSnapshot: ...

    def promote_checkpoint(self, command: PromoteCheckpoint) -> RuntimeThreadSnapshot: ...

    def mark_resumed(self, thread_id: str, event_key: str, worker_consumer: str) -> RuntimeThreadSnapshot: ...

    def mark_terminal(
        self,
        thread_id: str,
        *,
        event_key: str,
        worker_consumer: str,
        current_node: str | None,
        error_code: str | None = None,
    ) -> RuntimeThreadSnapshot: ...

    def update_last_event_sequence(self, thread_id: str, sequence: int) -> RuntimeThreadSnapshot: ...

    def list_events(self, thread_id: str, limit: int) -> Sequence[RuntimeThreadEventSnapshot]: ...


class RuntimeCheckpointStore(Protocol):
    async def setup(self) -> None: ...

    async def get_exact(self, thread_id: str, checkpoint_id: str) -> CheckpointRecord | None: ...

    async def list_bounded(self, thread_id: str, limit: int) -> Sequence[CheckpointRecord]: ...

    async def delete_thread(self, thread_id: str) -> None: ...

    def serialized_size(self, checkpoint: object) -> int: ...

    async def close(self) -> None: ...
