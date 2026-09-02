import asyncio

import pytest
from fakeredis.aioredis import FakeRedis, FakeServer
from redis.exceptions import RedisError

from app.runtime_overrides.redis_lock import RuntimeBoundaryLock, RuntimeBoundaryLockError

THREAD_ID = "cf:dispatch:TASK-0123456789abcdef0123456789abcde"


@pytest.mark.asyncio
async def test_runtime_override_thread_lock() -> None:
    server = FakeServer()
    first = RuntimeBoundaryLock(FakeRedis(server=server, decode_responses=False), ttl_ms=10_000)
    second = RuntimeBoundaryLock(FakeRedis(server=server, decode_responses=False), ttl_ms=10_000)

    first_handle = await first.acquire(THREAD_ID)
    second_handle = await second.acquire(THREAD_ID)

    assert first_handle.acquired is True
    assert second_handle.acquired is False
    assert first_handle.key == f"countyflow:lock:thread:{THREAD_ID}"


@pytest.mark.asyncio
async def test_runtime_override_thread_lock_release_is_token_safe() -> None:
    client = FakeRedis(decode_responses=False)
    lock = RuntimeBoundaryLock(client, ttl_ms=10_000)
    handle = await lock.acquire(THREAD_ID)

    assert await lock.release(handle.with_token("foreign")) is False
    assert await client.get(handle.key) == handle.token.encode()
    assert await lock.release(handle) is True


@pytest.mark.asyncio
async def test_runtime_override_thread_lock_recovers_after_ttl() -> None:
    client = FakeRedis(decode_responses=False)
    lock = RuntimeBoundaryLock(client, ttl_ms=20)
    assert (await lock.acquire(THREAD_ID)).acquired is True

    await asyncio.sleep(0.03)

    assert (await lock.acquire(THREAD_ID)).acquired is True


@pytest.mark.asyncio
async def test_runtime_override_thread_lock_normalizes_redis_errors(monkeypatch) -> None:
    client = FakeRedis(decode_responses=False)

    async def fail(*args, **kwargs):
        raise RedisError("redis://operator:secret@example.test")

    monkeypatch.setattr(client, "set", fail)

    with pytest.raises(RuntimeBoundaryLockError) as caught:
        await RuntimeBoundaryLock(client, ttl_ms=10_000).acquire(THREAD_ID)

    assert "secret" not in str(caught.value)
