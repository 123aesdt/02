import pytest
from fakeredis.aioredis import FakeRedis, FakeServer
from redis.exceptions import ConnectionError

from app.events.broker import EventBrokerConnectionError, EventBrokerMessageError, RedisTaskEventBroker
from app.events.models import TaskEvent, TaskEventType


def _event(event_type: TaskEventType = TaskEventType.TASK_ACCEPTED) -> TaskEvent:
    return TaskEvent.create("TASK-001", event_type, "test", "PENDING")


@pytest.mark.asyncio
async def test_redis_task_event_broker_cross_instance_delivery():
    server = FakeServer()
    publisher = RedisTaskEventBroker(FakeRedis(server=server, decode_responses=False), "countyflow:events:task", 100)
    reader = RedisTaskEventBroker(FakeRedis(server=server, decode_responses=False), "countyflow:events:task", 100)
    try:
        await publisher.publish(_event(TaskEventType.TASK_ACCEPTED))
        await publisher.publish(_event(TaskEventType.MEMORY_COMPLETED))
        await publisher.publish(_event(TaskEventType.ROUTING_COMPLETED))

        history = await reader.history("TASK-001")
        assert [event.event_type for event in history] == [
            TaskEventType.TASK_ACCEPTED,
            TaskEventType.MEMORY_COMPLETED,
            TaskEventType.ROUTING_COMPLETED,
        ]
    finally:
        await publisher.close()
        await reader.close()


@pytest.mark.asyncio
async def test_redis_task_event_sequence_is_monotonic_across_instances():
    server = FakeServer()
    brokers = [RedisTaskEventBroker(FakeRedis(server=server, decode_responses=False), "events", 100) for _ in range(3)]
    try:
        published = [await brokers[index % 3].publish(_event()) for index in range(5)]
        assert [event.sequence for event in published] == [1, 2, 3, 4, 5]
    finally:
        for broker in brokers:
            await broker.close()


@pytest.mark.asyncio
async def test_redis_task_event_history_replays_only_events_after_last_event_id():
    client = FakeRedis(decode_responses=False)
    broker = RedisTaskEventBroker(client, "events", 100)
    try:
        first = await broker.publish(_event())
        second = await broker.publish(_event(TaskEventType.MEMORY_COMPLETED))
        third = await broker.publish(_event(TaskEventType.ROUTING_COMPLETED))
        replay = await broker.history("TASK-001", after_event_id=first.event_id)
        assert [event.event_id for event in replay] == [second.event_id, third.event_id]
    finally:
        await broker.close()


@pytest.mark.asyncio
async def test_redis_task_event_retention_is_bounded():
    client = FakeRedis(decode_responses=False)
    broker = RedisTaskEventBroker(client, "events", 3)
    try:
        for _ in range(5):
            await broker.publish(_event())
        assert 1 <= len(await broker.history("TASK-001")) <= 3
    finally:
        await broker.close()


@pytest.mark.asyncio
async def test_redis_task_event_subscription_uses_xread_for_live_events():
    client = FakeRedis(decode_responses=False)
    broker = RedisTaskEventBroker(client, "events", 100, read_block_ms=10)
    try:
        first = await broker.publish(_event())
        subscription = await broker.subscribe("TASK-001", last_event_id=first.event_id)
        second = await broker.publish(_event(TaskEventType.WORKER_STARTED))
        assert [event.event_id for event in await subscription.read()] == [second.event_id]
    finally:
        await broker.close()


@pytest.mark.asyncio
async def test_redis_task_event_broker_normalizes_invalid_and_connection_errors():
    client = FakeRedis(decode_responses=False)
    broker = RedisTaskEventBroker(client, "events", 100)
    try:
        await client.xadd("events:TASK-001", {"data": "not-json"})
        with pytest.raises(EventBrokerMessageError, match="invalid"):
            await broker.history("TASK-001")
    finally:
        await broker.close()

    class FailingClient:
        async def incr(self, key):
            raise ConnectionError("redis://secret@internal unavailable")

    with pytest.raises(EventBrokerConnectionError) as error:
        await RedisTaskEventBroker(FailingClient(), "events", 100).publish(_event())
    assert "secret" not in str(error.value)
