import asyncio

import pytest
from fakeredis.aioredis import FakeRedis, FakeServer
from pydantic import ValidationError
from redis.exceptions import RedisError

from app.core.config import Settings
from app.shared_memory.redis_lock import MemoryMutationLock, MemoryMutationLockError

FACT_KEY = "smf_" + "a" * 64


@pytest.mark.asyncio
async def test_memory_mutation_lock_allows_only_one_holder() -> None:
    server = FakeServer()
    first = MemoryMutationLock(FakeRedis(server=server, decode_responses=False), ttl_ms=10_000)
    second = MemoryMutationLock(FakeRedis(server=server, decode_responses=False), ttl_ms=10_000)

    first_handle = await first.acquire(FACT_KEY)
    second_handle = await second.acquire(FACT_KEY)

    assert first_handle.acquired is True
    assert second_handle.acquired is False
    assert first_handle.key == f"countyflow:lock:memory:{FACT_KEY}"


@pytest.mark.asyncio
async def test_wrong_token_cannot_release_memory_lock() -> None:
    client = FakeRedis(decode_responses=False)
    lock = MemoryMutationLock(client, ttl_ms=10_000)
    handle = await lock.acquire(FACT_KEY)

    released = await lock.release(handle.with_token("wrong-owner"))

    assert released is False
    assert await client.get(handle.key) == handle.token.encode()


@pytest.mark.asyncio
async def test_memory_lock_recovers_after_ttl() -> None:
    client = FakeRedis(decode_responses=False)
    lock = MemoryMutationLock(client, ttl_ms=20)
    assert (await lock.acquire(FACT_KEY)).acquired is True

    await asyncio.sleep(0.03)

    assert (await lock.acquire(FACT_KEY)).acquired is True


@pytest.mark.asyncio
async def test_memory_lock_namespace_is_independent_from_dispatch_lock() -> None:
    client = FakeRedis(decode_responses=False)
    await client.set(f"countyflow:lock:dispatch:{FACT_KEY}", "dispatch", px=10_000)

    handle = await MemoryMutationLock(client, ttl_ms=10_000).acquire(FACT_KEY)

    assert handle.acquired is True


@pytest.mark.asyncio
async def test_memory_lock_normalizes_redis_error_without_secret(monkeypatch) -> None:
    client = FakeRedis(decode_responses=False)

    async def fail(*args, **kwargs):
        raise RedisError("redis://user:secret@example.test")

    monkeypatch.setattr(client, "set", fail)

    with pytest.raises(MemoryMutationLockError) as caught:
        await MemoryMutationLock(client, ttl_ms=10_000).acquire(FACT_KEY)

    assert "secret" not in str(caught.value)


def test_memory_lock_ttl_must_exceed_timeout_by_one_second() -> None:
    with pytest.raises(ValidationError, match="memory_mutation_lock_ttl_ms"):
        Settings(memory_mutation_timeout_seconds=5.0, memory_mutation_lock_ttl_ms=5_999)

    settings = Settings(memory_mutation_timeout_seconds=5.0, memory_mutation_lock_ttl_ms=6_000)
    assert settings.memory_mutation_lock_ttl_ms == 6_000

