import pytest
from fakeredis.aioredis import FakeRedis, FakeServer

from app.core.config import Settings
from app.events.broker import InMemoryTaskEventBroker, RedisTaskEventBroker
from app.events.factory import create_task_event_broker
from app.events.models import TaskEvent, TaskEventType


def test_event_broker_factory_memory():
    assert isinstance(create_task_event_broker(Settings(task_event_broker="memory"), FakeRedis()), InMemoryTaskEventBroker)


def test_event_broker_factory_redis():
    assert isinstance(create_task_event_broker(Settings(task_event_broker="redis"), FakeRedis()), RedisTaskEventBroker)


@pytest.mark.asyncio
async def test_api_and_worker_use_distinct_redis_brokers():
    server = FakeServer()
    api_broker = create_task_event_broker(Settings(task_event_broker="redis"), FakeRedis(server=server))
    worker_broker = create_task_event_broker(Settings(task_event_broker="redis"), FakeRedis(server=server))
    try:
        event = await api_broker.publish(TaskEvent.create("TASK-1", TaskEventType.TASK_ACCEPTED, "api", "PENDING"))
        assert api_broker is not worker_broker
        assert [item.event_id for item in await worker_broker.history("TASK-1")] == [event.event_id]
    finally:
        await api_broker.close()
        await worker_broker.close()
