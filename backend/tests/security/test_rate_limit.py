import asyncio

import pytest
from security_support import principal_for

from app.security.errors import SecurityHttpError
from app.security.rate_limit import (
    OperationClass,
    RateLimitAdmission,
    RateLimitPolicy,
    RedisTokenBucketRateLimiter,
)


class ScriptRedis:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result or [1, 29, 0, 15]
        self.error = error
        self.calls = []

    async def eval(self, script, key_count, key, *arguments):
        self.calls.append((script, key_count, key, arguments))
        if self.error:
            raise self.error
        return self.result


def policies() -> dict[OperationClass, RateLimitPolicy]:
    return {
        OperationClass.DISPATCH_SUBMIT: RateLimitPolicy(capacity=30, refill_per_minute=120),
        OperationClass.RUNTIME_OVERRIDE: RateLimitPolicy(capacity=3, refill_per_minute=12),
        OperationClass.MEMORY_MUTATION: RateLimitPolicy(capacity=5, refill_per_minute=30),
        OperationClass.OBSERVABILITY_READ: RateLimitPolicy(capacity=60, refill_per_minute=300),
        OperationClass.WS_TICKET: RateLimitPolicy(capacity=10, refill_per_minute=60),
    }


@pytest.mark.asyncio
async def test_rate_limit_per_principal() -> None:
    redis = ScriptRedis()
    limiter = RedisTokenBucketRateLimiter(redis, policies())

    await limiter.admit("supervisor-a", OperationClass.RUNTIME_OVERRIDE)
    await limiter.admit("supervisor-b", OperationClass.RUNTIME_OVERRIDE)

    first_key = redis.calls[0][2]
    second_key = redis.calls[1][2]
    assert first_key != second_key
    assert "supervisor-a" not in first_key
    assert "supervisor-b" not in second_key
    assert first_key.startswith("countyflow:ratelimit:")


@pytest.mark.asyncio
async def test_rate_limit_429() -> None:
    limiter = RedisTokenBucketRateLimiter(ScriptRedis([0, 0, 7, 15]), policies())

    decision = await limiter.admit("supervisor-a", OperationClass.RUNTIME_OVERRIDE)

    assert decision.allowed is False
    assert decision.retry_after_seconds == 7
    assert decision.remaining == 0


@pytest.mark.asyncio
async def test_rate_limit_retry_after() -> None:
    limiter = RedisTokenBucketRateLimiter(ScriptRedis([0, 0, 4, 12]), policies())
    admission = RateLimitAdmission(limiter, policies())

    with pytest.raises(SecurityHttpError) as captured:
        await admission.check(principal_for(), OperationClass.DISPATCH_SUBMIT)

    assert captured.value.status_code == 429
    assert captured.value.code == "RATE_LIMIT_EXCEEDED"
    assert captured.value.headers == {
        "Retry-After": "4",
        "X-RateLimit-Limit": "30",
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "12",
    }


@pytest.mark.asyncio
async def test_rate_limit_failure_high_risk_fails_closed() -> None:
    limiter = RedisTokenBucketRateLimiter(ScriptRedis(error=ConnectionError("redis endpoint detail")), policies())
    admission = RateLimitAdmission(limiter, policies())

    with pytest.raises(SecurityHttpError) as captured:
        await admission.check(principal_for(), OperationClass.MEMORY_MUTATION)

    assert captured.value.status_code == 503
    assert captured.value.code == "SECURITY_CONTROL_UNAVAILABLE"
    assert "redis" not in captured.value.message.lower()


def test_rate_limit_policy_validation() -> None:
    with pytest.raises(ValueError):
        RateLimitPolicy(capacity=0, refill_per_minute=1)
    with pytest.raises(ValueError):
        RateLimitPolicy(capacity=1, refill_per_minute=0)


def test_rate_limit_calls_are_async_safe() -> None:
    async def run() -> None:
        limiter = RedisTokenBucketRateLimiter(ScriptRedis(), policies())
        await asyncio.gather(
            *(limiter.admit("supervisor-a", OperationClass.RUNTIME_OVERRIDE) for _ in range(25))
        )

    asyncio.run(run())
