from app.runtime_threads.checkpoint_store import RuntimeCheckpointStoreError
from app.runtime_threads.models import RuntimeThreadEventType, RuntimeThreadSnapshot
from app.runtime_threads.protocols import RuntimeCheckpointStore, RuntimeThreadRepository
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission


class RuntimeThreadAuthorizationError(Exception):
    """Raised when runtime-thread metadata is not visible to the caller."""


class RuntimeThreadNotFoundError(Exception):
    pass


class RuntimeThreadStateUnavailableError(Exception):
    pass


class ThreadStateService:
    def __init__(
        self,
        repository: RuntimeThreadRepository,
        checkpoint_store: RuntimeCheckpointStore,
        *,
        history_max_limit: int = 100,
    ) -> None:
        self._repository = repository
        self._checkpoint_store = checkpoint_store
        self._history_max_limit = history_max_limit

    async def get_current_by_thread(self, thread_id: str, principal: AuthenticatedPrincipal) -> dict[str, object]:
        self._require_read(principal)
        thread = self._repository.get_by_thread_id(thread_id)
        return await self._current(thread)

    async def get_current_by_task(self, task_id: str, principal: AuthenticatedPrincipal) -> dict[str, object]:
        self._require_read(principal)
        thread = self._repository.get_by_task_id(task_id)
        return await self._current(thread)

    async def list_history(self, thread_id: str, principal: AuthenticatedPrincipal, *, limit: int) -> dict[str, object]:
        self._require_read(principal)
        thread = self._required(self._repository.get_by_thread_id(thread_id))
        bounded_limit = min(max(limit, 1), self._history_max_limit)
        events = self._repository.list_events(thread.thread_id, self._history_max_limit)
        checkpoint_events = sorted(
            (
                event
                for event in events
                if event.event_type
                in {
                    RuntimeThreadEventType.CHECKPOINT_PROMOTED,
                    RuntimeThreadEventType.RECONCILIATION,
                }
                and event.checkpoint_id is not None
            ),
            key=lambda event: event.state_version,
            reverse=True,
        )[:bounded_limit]
        items = []
        for event in checkpoint_events:
            record = await self._exact(thread.thread_id, event.checkpoint_id)
            items.append(
                {
                    "checkpoint_id": event.checkpoint_id,
                    "parent_checkpoint_id": event.parent_checkpoint_id,
                    "state_version": event.state_version,
                    "node": event.node,
                    "next_node": event.next_node,
                    "checkpoint_size_bytes": event.checkpoint_size_bytes,
                    "checkpoint_available": record is not None,
                    "state": record.state if record is not None else None,
                    "created_at": event.created_at,
                }
            )
        return {"thread_id": thread.thread_id, "items": items}

    async def _current(self, thread: RuntimeThreadSnapshot | None) -> dict[str, object]:
        current = self._required(thread)
        record = None
        if current.current_checkpoint_id is not None:
            record = await self._exact(current.thread_id, current.current_checkpoint_id)
        return {
            "thread_id": current.thread_id,
            "task_id": current.task_id,
            "status": current.status.value,
            "terminal": current.terminal,
            "current_checkpoint_id": current.current_checkpoint_id,
            "state_version": current.state_version,
            "current_node": current.current_node,
            "next_node": current.next_node,
            "checkpoint_count": current.checkpoint_count,
            "checkpoint_size_bytes": current.checkpoint_size_bytes,
            "last_event_sequence": current.last_event_sequence,
            "worker_consumer": current.worker_consumer,
            "checkpoint_available": record is not None,
            "state": record.state if record is not None else None,
            "created_at": current.created_at,
            "updated_at": current.updated_at,
            "terminal_at": current.terminal_at,
        }

    async def _exact(self, thread_id: str, checkpoint_id: str):
        try:
            return await self._checkpoint_store.get_exact(thread_id, checkpoint_id)
        except RuntimeCheckpointStoreError:
            raise RuntimeThreadStateUnavailableError from None

    @staticmethod
    def _required(thread: RuntimeThreadSnapshot | None) -> RuntimeThreadSnapshot:
        if thread is None:
            raise RuntimeThreadNotFoundError
        return thread

    @staticmethod
    def _require_read(principal: AuthenticatedPrincipal) -> None:
        if not principal.can(Permission.RUNTIME_READ):
            raise RuntimeThreadAuthorizationError


__all__ = [
    "RuntimeThreadAuthorizationError",
    "RuntimeThreadNotFoundError",
    "RuntimeThreadStateUnavailableError",
    "ThreadStateService",
]
