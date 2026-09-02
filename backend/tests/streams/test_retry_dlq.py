from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from redis.exceptions import ConnectionError

from app.streams.errors import QueueConnectionError
from app.streams.models import DeadLetterMessage, DispatchTaskMessage
from app.streams.redis_queue import RedisStreamQueue
from app.streams.retry import RetryPolicy

STREAM_NAME = "countyflow:test:retry"
DLQ_STREAM_NAME = "countyflow:test:dlq"
GROUP_NAME = "countyflow-retry-workers"
CONSUMER_NAME = "worker-retry-1"


@pytest_asyncio.fixture
async def redis_client():
    client = FakeRedis(decode_responses=False)
    yield client
    await client.aclose()


def _task() -> DispatchTaskMessage:
    return DispatchTaskMessage(
        schema_version="1",
        task_id="task-retry-001",
        order_id=1,
        anomaly_id=10,
        idempotency_key="idem-task-retry-001",
        created_at="2026-08-21T00:00:00+00:00",
        payload={
            "driver_id": "driver-li",
            "vehicle_id": "vehicle-001",
            "route_id": "xinping-road",
            "anomaly_type": "rain_slippery",
            "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
        },
    )


def _queue(redis_client: FakeRedis) -> RedisStreamQueue:
    return RedisStreamQueue(redis_client, STREAM_NAME, GROUP_NAME, CONSUMER_NAME, dlq_stream_name=DLQ_STREAM_NAME)


def test_retry_policy_allows_retry_before_limit():
    policy = RetryPolicy(max_delivery_attempts=3, base_delay_ms=100, max_delay_ms=500)

    assert policy.should_retry(1) is True
    assert policy.should_retry(2) is True


def test_retry_policy_rejects_retry_at_limit():
    policy = RetryPolicy(max_delivery_attempts=3, base_delay_ms=100, max_delay_ms=500)

    assert policy.should_retry(3) is False


def test_retry_backoff_increases_with_delivery_count():
    policy = RetryPolicy(max_delivery_attempts=8, base_delay_ms=100, max_delay_ms=10_000)

    assert [policy.backoff_ms(delivery_count) for delivery_count in (1, 2, 3)] == [100, 200, 400]


def test_retry_backoff_is_capped():
    policy = RetryPolicy(max_delivery_attempts=8, base_delay_ms=100, max_delay_ms=500)

    assert policy.backoff_ms(4) == 500
    assert policy.backoff_ms(5) == 500


def test_dead_letter_message_serialization():
    message = DeadLetterMessage.from_stream_message(
        original_message_id="1787314000000-0",
        stream_message=_task(),
        original_stream=STREAM_NAME,
        failure_reason="Graph execution did not complete.",
        error_code="GRAPH_EXECUTION_ERROR",
        delivery_count=3,
    )

    restored = DeadLetterMessage.from_json(message.to_json())

    assert restored == message
    assert datetime.fromisoformat(restored.failed_at).utcoffset() == UTC.utcoffset(datetime.now(UTC))


@pytest.mark.asyncio
async def test_move_to_dlq_preserves_original_identity(redis_client: FakeRedis):
    queue = _queue(redis_client)
    await queue.ensure_consumer_group()
    original_id = await queue.publish(_task())
    [pending] = await queue.read_group(count=1, block_ms=1)

    dlq_id = await queue.move_to_dlq(pending, "Graph execution did not complete.", "GRAPH_EXECUTION_ERROR", delivery_count=3)
    [(stored_id, fields)] = await redis_client.xrange(DLQ_STREAM_NAME)
    restored = DeadLetterMessage.from_json(fields[b"data"])

    assert dlq_id == stored_id.decode()
    assert restored.original_message_id == original_id
    assert restored.task_id == pending.task.task_id
    assert restored.order_id == pending.task.order_id
    assert restored.idempotency_key == pending.task.idempotency_key
    assert restored.payload == pending.task.payload
    assert restored.original_stream == STREAM_NAME


@pytest.mark.asyncio
async def test_move_to_dlq_acks_original_message(redis_client: FakeRedis):
    queue = _queue(redis_client)
    await queue.ensure_consumer_group()
    await queue.publish(_task())
    [pending] = await queue.read_group(count=1, block_ms=1)

    await queue.move_to_dlq(pending, "Graph execution did not complete.", "GRAPH_EXECUTION_ERROR", delivery_count=3)

    assert (await redis_client.xpending(STREAM_NAME, GROUP_NAME))["pending"] == 0


@pytest.mark.asyncio
async def test_move_to_dlq_does_not_ack_if_dlq_publish_fails(redis_client: FakeRedis, monkeypatch):
    queue = _queue(redis_client)
    await queue.ensure_consumer_group()
    await queue.publish(_task())
    [pending] = await queue.read_group(count=1, block_ms=1)
    acknowledged: list[str] = []

    async def failed_xadd(*args, **kwargs):
        raise ConnectionError("dlq offline")

    async def tracked_xack(name, groupname, *ids):
        acknowledged.extend(ids)
        return 1

    monkeypatch.setattr(redis_client, "xadd", failed_xadd)
    monkeypatch.setattr(redis_client, "xack", tracked_xack)

    with pytest.raises(QueueConnectionError):
        await queue.move_to_dlq(pending, "Graph execution did not complete.", "GRAPH_EXECUTION_ERROR", delivery_count=3)

    assert acknowledged == []
    assert (await redis_client.xpending(STREAM_NAME, GROUP_NAME))["pending"] == 1
