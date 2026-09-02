import asyncio
import json
from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from redis.exceptions import RedisError

from app.events.models import TaskEvent


class EventBrokerConnectionError(Exception):
    """Raised when the event transport cannot communicate with Redis."""


class EventBrokerMessageError(Exception):
    """Raised when a Redis event payload cannot be decoded safely."""


@dataclass(frozen=True)
class TaskEventSubscription:
    subscription_id: str
    task_id: str
    queue: asyncio.Queue[TaskEvent]

    async def read(self) -> list[TaskEvent]:
        return [await self.queue.get()]


class TaskEventBroker(Protocol):
    async def publish(self, event: TaskEvent) -> TaskEvent: ...

    async def subscribe(self, task_id: str, last_event_id: str | None = None): ...

    async def history(self, task_id: str, *, after_event_id: str | None = None) -> list[TaskEvent]: ...

    async def unsubscribe(self, subscription: TaskEventSubscription) -> None: ...


class RedisTaskEventSubscription:
    def __init__(self, broker: "RedisTaskEventBroker", task_id: str, cursor: str) -> None:
        self._broker = broker
        self.task_id = task_id
        self._cursor = cursor

    async def read(self) -> list[TaskEvent]:
        events = await self._broker._read_after(self.task_id, self._cursor)
        if events:
            self._cursor = events[-1].event_id
        return events


class RedisTaskEventBroker:
    """Redis Streams task-event transport for multi-process delivery and replay."""

    def __init__(self, client: object, stream_prefix: str, history_maxlen: int, *, read_block_ms: int = 1000) -> None:
        self._client = client
        self._stream_prefix = stream_prefix.rstrip(":")
        self._history_maxlen = history_maxlen
        self._read_block_ms = read_block_ms

    async def publish(self, event: TaskEvent) -> TaskEvent:
        try:
            sequence = await self._client.incr(self._sequence_key(event.task_id))
            serialized = json.dumps(event.with_sequence(sequence).to_dict(), ensure_ascii=False, separators=(",", ":"))
            stream_id = await self._client.xadd(
                self._stream_key(event.task_id),
                {"data": serialized},
                maxlen=self._history_maxlen,
                approximate=True,
            )
        except RedisError as error:
            raise EventBrokerConnectionError("Task event transport is temporarily unavailable.") from error
        return event.with_sequence(sequence).with_event_id(self._text(stream_id, "event ID"))

    async def history(self, task_id: str, *, after_event_id: str | None = None) -> list[TaskEvent]:
        try:
            entries = await self._client.xrange(self._stream_key(task_id), min="-", max="+")
        except RedisError as error:
            raise EventBrokerConnectionError("Task event transport is temporarily unavailable.") from error
        events = self._events(entries)
        return events if after_event_id is None else [event for event in events if event.event_id > after_event_id]

    async def subscribe(self, task_id: str, last_event_id: str | None = None) -> RedisTaskEventSubscription:
        return RedisTaskEventSubscription(self, task_id, last_event_id or "0-0")

    async def unsubscribe(self, subscription: RedisTaskEventSubscription) -> None:
        return None

    async def close(self) -> None:
        try:
            await self._client.aclose()
        except RedisError as error:
            raise EventBrokerConnectionError("Task event transport is temporarily unavailable.") from error

    async def _read_after(self, task_id: str, event_id: str) -> list[TaskEvent]:
        try:
            streams = await self._client.xread({self._stream_key(task_id): event_id}, block=self._read_block_ms)
        except RedisError as error:
            raise EventBrokerConnectionError("Task event transport is temporarily unavailable.") from error
        entries = [entry for _, stream_entries in streams for entry in stream_entries]
        return self._events(entries)

    def _events(self, entries: object) -> list[TaskEvent]:
        if not isinstance(entries, list):
            raise EventBrokerMessageError("Task event stream response is invalid.")
        events: list[TaskEvent] = []
        for entry in entries:
            if not isinstance(entry, tuple) or len(entry) != 2 or not isinstance(entry[1], Mapping):
                raise EventBrokerMessageError("Task event stream response is invalid.")
            raw_data = entry[1].get("data", entry[1].get(b"data"))
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode("utf-8")
            if not isinstance(raw_data, str):
                raise EventBrokerMessageError("Task event data is invalid.")
            try:
                payload = json.loads(raw_data)
                event = TaskEvent.from_dict(payload).with_event_id(self._text(entry[0], "event ID"))
            except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise EventBrokerMessageError("Task event data is invalid.") from error
            events.append(event)
        return events

    def _stream_key(self, task_id: str) -> str:
        return f"{self._stream_prefix}:{task_id}"

    def _sequence_key(self, task_id: str) -> str:
        return f"{self._stream_prefix}:seq:{task_id}"

    @staticmethod
    def _text(value: object, field: str) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        if isinstance(value, str) and value:
            return value
        raise EventBrokerMessageError(f"Task event {field} is invalid.")


class InMemoryTaskEventBroker:
    """Bounded, single-process broker; it is not a multi-process event bus."""

    def __init__(self, *, history_size: int = 100, subscriber_queue_size: int = 32) -> None:
        self._history_size = history_size
        self._subscriber_queue_size = subscriber_queue_size
        self._histories: dict[str, deque[TaskEvent]] = defaultdict(lambda: deque(maxlen=self._history_size))
        self._subscribers: dict[str, dict[str, asyncio.Queue[TaskEvent]]] = defaultdict(dict)

    async def publish(self, event: TaskEvent) -> TaskEvent:
        sequence = (self._histories[event.task_id][-1].sequence if self._histories[event.task_id] else 0) + 1
        published = event.with_sequence(sequence)
        self._histories[event.task_id].append(published)
        for queue in self._subscribers[event.task_id].values():
            self._offer(queue, published)
        return published

    async def subscribe(self, task_id: str, last_event_id: str | None = None) -> TaskEventSubscription:
        subscription_id = uuid4().hex
        queue: asyncio.Queue[TaskEvent] = asyncio.Queue(maxsize=self._subscriber_queue_size)
        self._subscribers[task_id][subscription_id] = queue
        for event in await self.history(task_id, after_event_id=last_event_id):
            self._offer(queue, event)
        return TaskEventSubscription(subscription_id, task_id, queue)

    async def history(self, task_id: str, *, after_event_id: str | None = None) -> list[TaskEvent]:
        history = list(self._histories[task_id])
        if after_event_id is None:
            return history
        for index, event in enumerate(history):
            if event.event_id == after_event_id:
                return history[index + 1 :]
        return history

    async def unsubscribe(self, subscription: TaskEventSubscription) -> None:
        subscribers = self._subscribers.get(subscription.task_id)
        if subscribers is None:
            return
        subscribers.pop(subscription.subscription_id, None)
        if not subscribers:
            self._subscribers.pop(subscription.task_id, None)

    async def subscriber_count(self, task_id: str) -> int:
        return len(self._subscribers.get(task_id, {}))

    def latest_sequence(self, task_id: str) -> int:
        history = self._histories.get(task_id)
        return history[-1].sequence if history else 0

    @staticmethod
    def _offer(queue: asyncio.Queue[TaskEvent], event: TaskEvent) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            queue.put_nowait(event)
