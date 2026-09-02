import asyncio
import hashlib
import os
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from app.security.models import AuthenticatedPrincipal, AuthMethod
from app.security.permissions import Permission, Role
from app.security.rate_limit import OperationClass, RateLimitPolicy, RedisTokenBucketRateLimiter
from app.security.revocation import RedisRevocationStore
from app.security.ws_ticket import RedisWsTicketService, WsTicketRejected

pytestmark = pytest.mark.asyncio
REDIS_URL = os.getenv("SECURITY_REDIS_URL")


@pytest_asyncio.fixture
async def redis_client():
    if not REDIS_URL:
        pytest.skip("SECURITY_REDIS_URL is required for real security Redis integration")
    client = Redis.from_url(REDIS_URL, decode_responses=False)
    await client.ping()
    yield client
    keys = []
    async for key in client.scan_iter(match="countyflow:test-security:*"):
        keys.append(key)
    if keys:
        await client.delete(*keys)
    await client.aclose()


def principal(subject: str = "real-redis-user") -> AuthenticatedPrincipal:
    now = datetime.now(UTC)
    return AuthenticatedPrincipal(
        subject_id=subject,
        display_name="Real Redis User",
        roles=frozenset({Role.ADMIN}),
        permissions=frozenset(Permission),
        auth_method=AuthMethod.DEVELOPMENT_JWT,
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
        jti=f"jti-{subject}",
    )


async def test_real_redis_ticket_is_digest_only_scoped_and_atomically_single_use(redis_client: Redis) -> None:
    service = RedisWsTicketService(
        redis_client,
        namespace="countyflow:test-security:ws-ticket",
        ttl_seconds=45,
    )
    issued = await service.issue(
        principal(),
        target_type="task",
        target_id="TASK-REAL-1",
        required_permission=Permission.DISPATCH_READ,
    )
    digest = hashlib.sha256(issued.ticket.encode("ascii")).hexdigest()
    keys = [key.decode() async for key in redis_client.scan_iter(match="countyflow:test-security:ws-ticket:*")]
    assert keys == [f"countyflow:test-security:ws-ticket:{digest}"]
    assert issued.ticket not in keys[0]
    assert 1 <= await redis_client.ttl(keys[0]) <= 45

    results = await asyncio.gather(
        *(service.consume(
            issued.ticket,
            target_type="task",
            target_id="TASK-REAL-1",
            required_permission=Permission.DISPATCH_READ,
        ) for _ in range(20)),
        return_exceptions=True,
    )
    assert sum(not isinstance(value, Exception) for value in results) == 1
    assert all(
        not isinstance(value, WsTicketRejected) or value.code == "WS_TICKET_REPLAYED_OR_EXPIRED"
        for value in results
    )

    wrong_scope = await service.issue(
        principal(),
        target_type="task",
        target_id="TASK-REAL-A",
        required_permission=Permission.DISPATCH_READ,
    )
    with pytest.raises(WsTicketRejected, match="WS_TICKET_WRONG_SCOPE"):
        await service.consume(
            wrong_scope.ticket,
            target_type="task",
            target_id="TASK-REAL-B",
            required_permission=Permission.DISPATCH_READ,
        )


async def test_real_redis_token_bucket_is_atomic_and_isolated_by_principal(redis_client: Redis) -> None:
    policy = RateLimitPolicy(capacity=5, refill_per_minute=1)
    limiter = RedisTokenBucketRateLimiter(
        redis_client,
        {OperationClass.RUNTIME_OVERRIDE: policy},
        namespace="countyflow:test-security:ratelimit",
    )
    decisions = await asyncio.gather(
        *(limiter.admit("subject-a", OperationClass.RUNTIME_OVERRIDE) for _ in range(40))
    )
    assert sum(decision.allowed for decision in decisions) == 5
    assert all(decision.remaining >= 0 for decision in decisions)
    isolated = await limiter.admit("subject-b", OperationClass.RUNTIME_OVERRIDE)
    assert isolated.allowed is True
    assert isolated.remaining == 4


async def test_real_redis_revocation_uses_digest_and_bounded_ttl(redis_client: Redis) -> None:
    store = RedisRevocationStore(redis_client, namespace="countyflow:test-security:revoked")
    jti = "raw-jti-must-not-be-a-key"
    await store.revoke(jti, datetime.now(UTC) + timedelta(seconds=30))
    assert await store.is_revoked(jti) is True
    keys = [key.decode() async for key in redis_client.scan_iter(match="countyflow:test-security:revoked:*")]
    assert len(keys) == 1
    assert jti not in keys[0]
    assert 1 <= await redis_client.ttl(keys[0]) <= 30
