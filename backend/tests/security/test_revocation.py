from datetime import UTC, datetime, timedelta

import fakeredis.aioredis
import pytest

from app.security.revocation import RedisRevocationStore


@pytest.mark.asyncio
async def test_revocation_uses_digest_key_and_remaining_lifetime() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    store = RedisRevocationStore(redis, namespace="countyflow:auth:revoked")
    expires_at = datetime.now(UTC) + timedelta(seconds=60)

    await store.revoke("raw-session-identifier", expires_at)

    keys = [key async for key in redis.scan_iter(match="countyflow:auth:revoked:*")]
    assert len(keys) == 1
    assert b"raw-session-identifier" not in keys[0]
    ttl = await redis.ttl(keys[0])
    assert 0 < ttl <= 60
    assert await store.is_revoked("raw-session-identifier") is True
    assert await store.is_revoked("different-session") is False


@pytest.mark.asyncio
async def test_expired_revocation_is_not_persisted() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    store = RedisRevocationStore(redis)

    await store.revoke("expired-session", datetime.now(UTC) - timedelta(seconds=1))

    assert await store.is_revoked("expired-session") is False

