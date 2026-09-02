from collections.abc import Mapping

from app.events.broker import TaskEventBroker
from app.events.graph_adapter import GraphEventAdapter
from app.events.models import TaskEvent, TaskEventType
from app.runtime_threads.models import RuntimeThreadSnapshot
from app.runtime_threads.protocols import RuntimeThreadRepository


class RuntimeThreadEventPublisher:
    def __init__(self, broker: TaskEventBroker, repository: RuntimeThreadRepository) -> None:
        self._broker = broker
        self._repository = repository
        self._graph_events = GraphEventAdapter(broker)

    async def start(self, thread: RuntimeThreadSnapshot) -> None:
        if thread.next_node is not None:
            await self._graph_events.publish_started(thread.task_id, thread.next_node)

    async def __call__(
        self,
        thread: RuntimeThreadSnapshot,
        node: str | None = None,
        patch: Mapping[str, object] | None = None,
        state: Mapping[str, object] | None = None,
    ) -> TaskEvent:
        if node is not None:
            await self._graph_events.publish_completed(thread.task_id, node, patch or {}, state)
        published = await self.publish_checkpoint(thread)
        if thread.next_node is not None:
            await self._graph_events.publish_started(thread.task_id, thread.next_node)
        return published

    async def publish_checkpoint(self, thread: RuntimeThreadSnapshot) -> TaskEvent:
        event = TaskEvent.create(
            thread.task_id,
            TaskEventType.THREAD_CHECKPOINTED,
            "runtime_thread",
            "STABLE",
            data=self._checkpoint_data(thread),
        )
        return await self._publish(thread.thread_id, event)

    async def publish_resumed(self, thread: RuntimeThreadSnapshot) -> TaskEvent:
        event = TaskEvent.create(
            thread.task_id,
            TaskEventType.THREAD_RESUMED,
            "runtime_thread",
            "PROCESSING",
            data={**self._checkpoint_data(thread), "resume_count": thread.resumed_count},
        )
        return await self._publish(thread.thread_id, event)

    async def publish_terminal(self, thread: RuntimeThreadSnapshot) -> TaskEvent:
        event = TaskEvent.create(
            thread.task_id,
            TaskEventType.THREAD_TERMINAL,
            "runtime_thread",
            "TERMINAL",
            data=self._checkpoint_data(thread),
        )
        return await self._publish(thread.thread_id, event)

    async def _publish(self, thread_id: str, event: TaskEvent) -> TaskEvent:
        published = await self._broker.publish(event)
        self._repository.update_last_event_sequence(thread_id, published.sequence)
        return published

    @staticmethod
    def _checkpoint_data(thread: RuntimeThreadSnapshot) -> dict[str, object]:
        return {
            "thread_id": thread.thread_id,
            "checkpoint_id": thread.current_checkpoint_id,
            "state_version": thread.state_version,
            "node": thread.current_node,
            "next_node": thread.next_node,
            "checkpoint_size_bytes": thread.checkpoint_size_bytes,
        }
