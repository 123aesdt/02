import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from redis.exceptions import ConnectionError

from app.streams.errors import QueueConnectionError, QueueMessageError
from app.streams.models import DispatchTaskMessage
from app.streams.redis_queue import RedisStreamQueue

STREAM_NAME = "countyflow:test:tasks"
GROUP_NAME = "countyflow-test-workers"
CONSUMER_NAME = "test-worker-1"


@pytest_asyncio.fixture
async def redis_client():
    client = FakeRedis(decode_responses=False)
    yield client
    await client.aclose()


def _task(task_id: str = "task-001") -> DispatchTaskMessage:
    return DispatchTaskMessage(
        schema_version="1",
        task_id=task_id,
        order_id=1,
        anomaly_id=10,
        idempotency_key=f"idem-{task_id}",
        created_at="2026-08-21T00:00:00+00:00",
        payload={
            "driver_id": "driver-li",
            "vehicle_id": "vehicle-001",
            "route_id": "xinping-road",
            "anomaly_type": "rain_slippery",
            "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
            "vehicle_status": "NORMAL",
        },
    )


def _queue(redis_client: FakeRedis) -> RedisStreamQueue:
    return RedisStreamQueue(redis_client, STREAM_NAME, GROUP_NAME, CONSUMER_NAME)


def test_task_message_serialization():
    task = _task()

    restored = DispatchTaskMessage.from_json(task.to_json())

    assert restored == task


@pytest.mark.asyncio
async def test_stream_publish(redis_client: FakeRedis):
    queue = _queue(redis_client)

    message_id = await queue.publish(_task())
    entries = await redis_client.xrange(STREAM_NAME)

    assert message_id
    assert len(entries) == 1
    assert DispatchTaskMessage.from_json(entries[0][1][b"data"].decode()) == _task()


@pytest.mark.asyncio
async def test_consumer_group_creation_is_idempotent(redis_client: FakeRedis):
    queue = _queue(redis_client)

    assert await queue.ensure_consumer_group() is True
    assert await queue.ensure_consumer_group() is False


@pytest.mark.asyncio
async def test_stream_read_group(redis_client: FakeRedis):
    queue = _queue(redis_client)
    await queue.ensure_consumer_group()
    await queue.publish(_task("task-001"))
    await queue.publish(_task("task-002"))
    await queue.publish(_task("task-003"))

    messages = await queue.read_group(count=3, block_ms=1)

    assert [message.task.task_id for message in messages] == ["task-001", "task-002", "task-003"]
    assert [message.task.idempotency_key for message in messages] == ["idem-task-001", "idem-task-002", "idem-task-003"]
    assert all(message.message_id for message in messages)
    assert all(message.metadata["stream"] == STREAM_NAME for message in messages)


@pytest.mark.asyncio
async def test_stream_ack(redis_client: FakeRedis):
    queue = _queue(redis_client)
    await queue.ensure_consumer_group()
    await queue.publish(_task())
    [message] = await queue.read_group(count=1, block_ms=1)

    pending_before_ack = await redis_client.xpending(STREAM_NAME, GROUP_NAME)
    acknowledged = await queue.ack(message.message_id)
    pending_after_ack = await redis_client.xpending(STREAM_NAME, GROUP_NAME)

    assert pending_before_ack["pending"] == 1
    assert acknowledged == 1
    assert pending_after_ack["pending"] == 0


@pytest.mark.asyncio
async def test_stream_message_mapping(redis_client: FakeRedis):
    queue = _queue(redis_client)
    await queue.ensure_consumer_group()
    message_id = await queue.publish(_task())

    [message] = await queue.read_group(count=1, block_ms=1)

    assert message.message_id == message_id
    assert message.task.order_id == 1
    assert message.task.payload["route_id"] == "xinping-road"


@pytest.mark.asyncio
@pytest.mark.parametrize("data", ["{", '{"schema_version":"2"}', '{"schema_version":"1"}'])
async def test_stream_invalid_message(redis_client: FakeRedis, data: str):
    queue = _queue(redis_client)
    await queue.ensure_consumer_group()
    await redis_client.xadd(STREAM_NAME, {"data": data})

    with pytest.raises(QueueMessageError):
        await queue.read_group(count=1, block_ms=1)


@pytest.mark.asyncio
async def test_stream_redis_error_is_normalized():
    class FailingRedis:
        async def xadd(self, stream: str, fields: dict[str, str]) -> str:
            raise ConnectionError("redis offline")

    queue = RedisStreamQueue(FailingRedis(), STREAM_NAME, GROUP_NAME, CONSUMER_NAME)

    with pytest.raises(QueueConnectionError) as error:
        await queue.publish(_task())

    assert "redis offline" not in str(error.value)
