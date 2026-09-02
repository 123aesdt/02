import asyncio

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from redis.exceptions import ConnectionError

from app.locks.redis_execution_lock import ExecutionLockError, RedisExecutionLock


@pytest_asyncio.fixture
async def redis_client():
    client = FakeRedis(decode_responses=False)
    yield client
    await client.aclose()


@pytest.mark.asyncio
async def test_execution_lock_first_acquire_succeeds(redis_client: FakeRedis):
    handle = await RedisExecutionLock(redis_client, ttl_ms=100).acquire("idem-001")

    assert (handle.key, handle.acquired, bool(handle.token)) == ("countyflow:lock:dispatch:idem-001", True, True)


@pytest.mark.asyncio
async def test_execution_lock_second_acquire_fails(redis_client: FakeRedis):
    lock = RedisExecutionLock(redis_client, ttl_ms=100)
    await lock.acquire("idem-001")

    second = await lock.acquire("idem-001")

    assert second.acquired is False


@pytest.mark.asyncio
async def test_execution_lock_wrong_token_cannot_release(redis_client: FakeRedis):
    lock = RedisExecutionLock(redis_client, ttl_ms=100)
    handle = await lock.acquire("idem-001")
    wrong_token_handle = handle.with_token("wrong-token")

    released = await lock.release(wrong_token_handle)

    assert released is False


@pytest.mark.asyncio
async def test_execution_lock_correct_token_releases(redis_client: FakeRedis):
    lock = RedisExecutionLock(redis_client, ttl_ms=100)
    handle = await lock.acquire("idem-001")

    released = await lock.release(handle)

    assert released is True


@pytest.mark.asyncio
async def test_execution_lock_can_be_reacquired_after_release(redis_client: FakeRedis):
    lock = RedisExecutionLock(redis_client, ttl_ms=100)
    first = await lock.acquire("idem-001")
    await lock.release(first)

    second = await lock.acquire("idem-001")

    assert second.acquired is True


@pytest.mark.asyncio
async def test_execution_lock_can_be_reacquired_after_ttl(redis_client: FakeRedis):
    lock = RedisExecutionLock(redis_client, ttl_ms=10)
    await lock.acquire("idem-001")
    await asyncio.sleep(0.05)

    second = await lock.acquire("idem-001")

    assert second.acquired is True


@pytest.mark.asyncio
async def test_execution_lock_normalizes_redis_errors(redis_client: FakeRedis, monkeypatch):
    async def failed_set(*args, **kwargs):
        raise ConnectionError("redis://user:password@host unavailable")

    monkeypatch.setattr(redis_client, "set", failed_set)

    with pytest.raises(ExecutionLockError, match="execution lock acquire failed") as error:
        await RedisExecutionLock(redis_client, ttl_ms=100).acquire("idem-001")

    assert "password" not in str(error.value)
