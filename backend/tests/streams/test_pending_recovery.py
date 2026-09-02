import asyncio

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis

from app.streams.models import DispatchTaskMessage
from app.streams.redis_queue import RedisStreamQueue

STREAM_NAME = "countyflow:test:pending"
GROUP_NAME = "countyflow-pending-workers"


@pytest_asyncio.fixture
async def redis_client():
    client = FakeRedis(decode_responses=False)
    yield client
    await client.aclose()


def _task(task_id: str = "task-pending-001") -> DispatchTaskMessage:
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
        },
    )


def _queue(redis_client: FakeRedis, consumer_name: str) -> RedisStreamQueue:
    return RedisStreamQueue(redis_client, STREAM_NAME, GROUP_NAME, consumer_name)


@pytest.mark.asyncio
async def test_pending_message_is_not_lost(redis_client: FakeRedis):
    worker_a = _queue(redis_client, "worker-a")
    await worker_a.ensure_consumer_group()
    message_id = await worker_a.publish(_task())
    [pending_message] = await worker_a.read_group(count=1, block_ms=1)

    summary = await worker_a.get_pending_summary()

    assert pending_message.message_id == message_id
    assert summary.pending == 1
    assert summary.min_message_id == message_id


@pytest.mark.asyncio
async def test_xautoclaim_reclaims_idle_message(redis_client: FakeRedis):
    worker_a = _queue(redis_client, "worker-a")
    worker_b = _queue(redis_client, "worker-b")
    await worker_a.ensure_consumer_group()
    original_id = await worker_a.publish(_task())
    await worker_a.read_group(count=1, block_ms=1)
    await asyncio.sleep(1.1)

    recovered = await worker_b.claim_pending(consumer_name="worker-b", min_idle_ms=1, start_id="0-0", count=10)

    assert [message.message_id for message in recovered] == [original_id]


@pytest.mark.asyncio
async def test_xautoclaim_does_not_claim_fresh_message(redis_client: FakeRedis):
    worker_a = _queue(redis_client, "worker-a")
    worker_b = _queue(redis_client, "worker-b")
    await worker_a.ensure_consumer_group()
    await worker_a.publish(_task())
    await worker_a.read_group(count=1, block_ms=1)

    recovered = await worker_b.claim_pending(consumer_name="worker-b", min_idle_ms=60_000, start_id="0-0", count=10)

    assert recovered == []


@pytest.mark.asyncio
async def test_recovered_message_preserves_original_message_id(redis_client: FakeRedis):
    worker_a = _queue(redis_client, "worker-a")
    worker_b = _queue(redis_client, "worker-b")
    await worker_a.ensure_consumer_group()
    original_id = await worker_a.publish(_task("task-original-id"))
    await worker_a.read_group(count=1, block_ms=1)
    await asyncio.sleep(1.1)

    [recovered] = await worker_b.claim_pending(consumer_name="worker-b", min_idle_ms=1, start_id="0-0", count=10)

    assert recovered.message_id == original_id
    assert recovered.task.task_id == "task-original-id"
    assert recovered.task.idempotency_key == "idem-task-original-id"
