from collections.abc import Mapping
from typing import Protocol

from redis.exceptions import RedisError, ResponseError

from app.streams.errors import QueueConnectionError, QueueMessageError
from app.streams.models import DeadLetterMessage, DispatchTaskMessage, PendingSummary, StreamMessage, StreamOperationalState

DEFAULT_DLQ_STREAM_NAME = "countyflow:dispatch:dlq"


class RedisStreamClient(Protocol):
    async def xgroup_create(
        self,
        name: str,
        groupname: str,
        id: str = "0-0",
        *,
        mkstream: bool = False,
    ) -> object: ...

    async def xadd(self, name: str, fields: Mapping[str, str]) -> str | bytes: ...

    async def xreadgroup(
        self,
        groupname: str,
        consumername: str,
        streams: Mapping[str, str],
        *,
        count: int,
        block: int,
    ) -> object: ...

    async def xack(self, name: str, groupname: str, *ids: str) -> int: ...

    async def xpending(self, name: str, groupname: str) -> object: ...

    async def xpending_range(
        self,
        name: str,
        groupname: str,
        min: str,
        max: str,
        count: int,
        consumername: str | None = None,
    ) -> object: ...

    async def xautoclaim(
        self,
        name: str,
        groupname: str,
        consumername: str,
        min_idle_time: int,
        start_id: str = "0-0",
        count: int | None = None,
    ) -> object: ...

    async def xinfo_groups(self, name: str) -> object: ...

    async def xlen(self, name: str) -> int: ...

    async def aclose(self) -> None: ...


class RedisStreamQueue:
    def __init__(
        self,
        client: RedisStreamClient,
        stream_name: str,
        consumer_group: str,
        consumer_name: str,
        *,
        dlq_stream_name: str = DEFAULT_DLQ_STREAM_NAME,
    ) -> None:
        self._client = client
        self._stream_name = stream_name
        self._consumer_group = consumer_group
        self._consumer_name = consumer_name
        self._dlq_stream_name = dlq_stream_name

    async def ensure_consumer_group(self) -> bool:
        try:
            await self._client.xgroup_create(
                self._stream_name,
                self._consumer_group,
                id="0-0",
                mkstream=True,
            )
        except ResponseError as error:
            if "BUSYGROUP" in str(error):
                return False
            raise QueueConnectionError("Redis consumer group initialization failed.") from error
        except RedisError as error:
            raise QueueConnectionError("Redis consumer group initialization failed.") from error
        return True

    async def publish(self, task: DispatchTaskMessage) -> str:
        try:
            message_id = await self._client.xadd(self._stream_name, {"data": task.to_json()})
        except RedisError as error:
            raise QueueConnectionError("Redis stream publish failed.") from error
        return self._text(message_id, "message ID")

    async def read_group(self, *, count: int, block_ms: int) -> list[StreamMessage]:
        try:
            streams = await self._client.xreadgroup(
                self._consumer_group,
                self._consumer_name,
                {self._stream_name: ">"},
                count=count,
                block=block_ms,
            )
        except RedisError as error:
            raise QueueConnectionError("Redis stream read failed.") from error
        return [message for stream, entries in streams for message in self._messages(stream, entries)]

    async def ack(self, message_id: str) -> int:
        try:
            return await self._client.xack(self._stream_name, self._consumer_group, message_id)
        except RedisError as error:
            raise QueueConnectionError("Redis stream acknowledgement failed.") from error

    async def publish_dead_letter(self, dead_letter: DeadLetterMessage) -> str:
        try:
            message_id = await self._client.xadd(self._dlq_stream_name, {"data": dead_letter.to_json()})
        except RedisError as error:
            raise QueueConnectionError("Redis dead-letter publish failed.") from error
        return self._text(message_id, "dead-letter message ID")

    async def move_to_dlq(
        self,
        stream_message: StreamMessage,
        failure_reason: str,
        error_code: str,
        *,
        delivery_count: int,
    ) -> str:
        dead_letter = DeadLetterMessage.from_stream_message(
            original_message_id=stream_message.message_id,
            stream_message=stream_message.task,
            original_stream=self._stream_name,
            failure_reason=failure_reason,
            error_code=error_code,
            delivery_count=delivery_count,
        )
        dlq_message_id = await self.publish_dead_letter(dead_letter)
        await self.ack(stream_message.message_id)
        return dlq_message_id

    async def get_pending_summary(self) -> PendingSummary:
        try:
            raw = await self._client.xpending(self._stream_name, self._consumer_group)
        except RedisError as error:
            raise QueueConnectionError("Redis pending summary read failed.") from error
        if not isinstance(raw, Mapping):
            raise QueueMessageError("Redis pending summary is invalid.")
        pending = raw.get("pending", raw.get(b"pending"))
        minimum = raw.get("min", raw.get(b"min"))
        maximum = raw.get("max", raw.get(b"max"))
        consumers = raw.get("consumers", raw.get(b"consumers"))
        if not isinstance(pending, int) or isinstance(pending, bool):
            raise QueueMessageError("Redis pending count is invalid.")
        if not isinstance(consumers, list):
            raise QueueMessageError("Redis pending consumers are invalid.")
        return PendingSummary(
            pending=pending,
            min_message_id=self._optional_text(minimum, "pending minimum message ID"),
            max_message_id=self._optional_text(maximum, "pending maximum message ID"),
            consumers=self._pending_consumers(consumers),
        )

    async def get_operational_state(self) -> StreamOperationalState:
        pending = await self.get_pending_summary()
        try:
            groups = await self._client.xinfo_groups(self._stream_name)
            dlq_messages = await self._client.xlen(self._dlq_stream_name)
        except RedisError as error:
            raise QueueConnectionError("Redis stream operational state read failed.") from error
        if not isinstance(groups, list) or not isinstance(dlq_messages, int) or isinstance(dlq_messages, bool):
            raise QueueMessageError("Redis stream operational state is invalid.")
        lag: int | None = None
        for group in groups:
            if not isinstance(group, Mapping):
                continue
            name = group.get("name", group.get(b"name"))
            if self._optional_text(name, "consumer group") != self._consumer_group:
                continue
            value = group.get("lag", group.get(b"lag"))
            if isinstance(value, int) and not isinstance(value, bool):
                lag = value
                break
        if lag is None:
            raise QueueMessageError("Redis consumer group lag is unavailable.")
        return StreamOperationalState(dict(pending.consumers), lag, dlq_messages)

    async def claim_pending(
        self,
        *,
        consumer_name: str | None = None,
        min_idle_ms: int,
        start_id: str = "0-0",
        count: int,
    ) -> list[StreamMessage]:
        recovery_consumer = consumer_name or self._consumer_name
        pending_idle = await self._pending_idle_times(count)
        try:
            raw = await self._client.xautoclaim(
                self._stream_name,
                self._consumer_group,
                recovery_consumer,
                min_idle_ms,
                start_id,
                count=count,
            )
        except RedisError as error:
            raise QueueConnectionError("Redis pending message recovery failed.") from error
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            raise QueueMessageError("Redis pending recovery response is invalid.")
        messages = self._messages(self._stream_name, raw[1])
        delivery_counts = await self._delivery_counts(messages, recovery_consumer)
        return [
            StreamMessage(
                message.message_id,
                message.task,
                delivery_counts.get(message.message_id),
                {**message.metadata, "pending_idle_ms_at_claim": str(pending_idle.get(message.message_id, 0))},
            )
            for message in messages
        ]

    async def close(self) -> None:
        try:
            await self._client.aclose()
        except RedisError as error:
            raise QueueConnectionError("Redis client close failed.") from error

    def _messages(self, stream: object, entries: object) -> list[StreamMessage]:
        if not isinstance(entries, list):
            raise QueueMessageError("Redis stream entries are invalid.")
        stream_name = self._text(stream, "stream name")
        messages: list[StreamMessage] = []
        for entry in entries:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise QueueMessageError("Redis stream entry is invalid.")
            message_id, fields = entry
            if not isinstance(fields, Mapping):
                raise QueueMessageError("Redis stream fields are invalid.")
            data = fields.get(b"data", fields.get("data"))
            if not isinstance(data, (str, bytes)):
                raise QueueMessageError("Redis stream message data is required.")
            messages.append(
                StreamMessage(
                    message_id=self._text(message_id, "message ID"),
                    task=DispatchTaskMessage.from_json(data),
                    delivery_count=None,
                    metadata={"stream": stream_name},
                )
            )
        return messages

    async def _delivery_counts(self, messages: list[StreamMessage], consumer_name: str) -> dict[str, int]:
        if not messages:
            return {}
        try:
            raw = await self._client.xpending_range(
                self._stream_name,
                self._consumer_group,
                "-",
                "+",
                len(messages),
                consumername=consumer_name,
            )
        except (RedisError, ResponseError):
            return {}
        if not isinstance(raw, list):
            return {}
        counts: dict[str, int] = {}
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            message_id = item.get("message_id", item.get(b"message_id"))
            delivered = item.get("times_delivered", item.get(b"times_delivered"))
            if isinstance(delivered, int) and not isinstance(delivered, bool):
                try:
                    counts[self._text(message_id, "pending message ID")] = delivered
                except QueueMessageError:
                    continue
        return counts

    async def _pending_idle_times(self, count: int) -> dict[str, int]:
        try:
            raw = await self._client.xpending_range(self._stream_name, self._consumer_group, "-", "+", count)
        except (RedisError, ResponseError):
            return {}
        if not isinstance(raw, list):
            return {}
        idle_times: dict[str, int] = {}
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            message_id = item.get("message_id", item.get(b"message_id"))
            idle = item.get("time_since_delivered", item.get(b"time_since_delivered"))
            if isinstance(idle, int) and not isinstance(idle, bool):
                try:
                    idle_times[self._text(message_id, "pending message ID")] = idle
                except QueueMessageError:
                    continue
        return idle_times

    def _pending_consumers(self, consumers: list[object]) -> dict[str, int]:
        mapped: dict[str, int] = {}
        for consumer in consumers:
            if not isinstance(consumer, Mapping):
                raise QueueMessageError("Redis pending consumer is invalid.")
            name = consumer.get("name", consumer.get(b"name"))
            pending = consumer.get("pending", consumer.get(b"pending"))
            if not isinstance(pending, int) or isinstance(pending, bool):
                raise QueueMessageError("Redis pending consumer count is invalid.")
            mapped[self._text(name, "pending consumer name")] = pending
        return mapped

    @staticmethod
    def _text(value: object, field: str) -> str:
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except UnicodeDecodeError as error:
                raise QueueMessageError(f"Redis {field} is not UTF-8.") from error
        if isinstance(value, str) and value:
            return value
        raise QueueMessageError(f"Redis {field} is invalid.")

    @classmethod
    def _optional_text(cls, value: object, field: str) -> str | None:
        if value is None:
            return None
        return cls._text(value, field)
