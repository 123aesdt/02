import asyncio
import hashlib
import math
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from fastapi import Request

from app.security.audit import SecurityAuditEventType, SecurityAuditStatus
from app.security.dependencies import PrincipalDependency
from app.security.errors import SecurityHttpError
from app.security.metrics import record_security_metric
from app.security.models import AuthenticatedPrincipal
from app.security.security_audit import SecurityAuditUnavailable


class OperationClass(StrEnum):
    DISPATCH_SUBMIT = "dispatch_submit"
    RUNTIME_OVERRIDE = "runtime_override"
    MEMORY_MUTATION = "memory_mutation"
    OBSERVABILITY_READ = "observability_read"
    WS_TICKET = "ws_ticket"
    AUTHENTICATION_INVALID = "authentication_invalid"


@dataclass(frozen=True)
class RateLimitPolicy:
    capacity: int
    refill_per_minute: int

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("rate-limit capacity must be positive")
        if self.refill_per_minute <= 0:
            raise ValueError("rate-limit refill must be positive")


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int
    reset_after_seconds: int


class RateLimiterUnavailable(Exception):
    """Raised when the distributed security admission control cannot decide."""


class RateLimiter(Protocol):
    async def admit(self, subject_id: str, operation: OperationClass) -> RateLimitDecision: ...


TOKEN_BUCKET_LUA = """
local bucket_key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_ms = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local ttl_ms = tonumber(ARGV[4])
local server_time = redis.call('TIME')
local now_ms = (tonumber(server_time[1]) * 1000) + math.floor(tonumber(server_time[2]) / 1000)
local state = redis.call('HMGET', bucket_key, 'tokens', 'updated_ms')
local tokens = tonumber(state[1]) or capacity
local updated_ms = tonumber(state[2]) or now_ms
local elapsed_ms = math.max(0, now_ms - updated_ms)
tokens = math.min(capacity, tokens + (elapsed_ms * refill_per_ms))
local allowed = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end
redis.call('HSET', bucket_key, 'tokens', tostring(tokens), 'updated_ms', tostring(now_ms))
redis.call('PEXPIRE', bucket_key, ttl_ms)
local missing = math.max(0, cost - tokens)
local retry_seconds = 0
if allowed == 0 then
  retry_seconds = math.max(1, math.ceil((missing / refill_per_ms) / 1000))
end
local reset_seconds = math.max(1, math.ceil(((capacity - tokens) / refill_per_ms) / 1000))
return {allowed, math.floor(tokens), retry_seconds, reset_seconds}
"""


class RedisTokenBucketRateLimiter:
    def __init__(
        self,
        redis,
        policies: dict[OperationClass, RateLimitPolicy],
        *,
        namespace: str = "countyflow:ratelimit",
    ) -> None:
        normalized = namespace.strip().strip(":")
        if not normalized:
            raise ValueError("rate-limit namespace must not be empty")
        self._redis = redis
        self._policies = dict(policies)
        self._namespace = normalized

    async def admit(self, subject_id: str, operation: OperationClass) -> RateLimitDecision:
        policy = self._policies[operation]
        key = self._key(subject_id, operation)
        refill_per_ms = policy.refill_per_minute / 60_000
        ttl_ms = max(60_000, math.ceil((policy.capacity / policy.refill_per_minute) * 120_000))
        try:
            raw = await self._redis.eval(
                TOKEN_BUCKET_LUA,
                1,
                key,
                policy.capacity,
                refill_per_ms,
                1,
                ttl_ms,
            )
            allowed, remaining, retry_after, reset_after = (int(value) for value in raw)
        except Exception as error:
            raise RateLimiterUnavailable from error
        return RateLimitDecision(
            allowed=bool(allowed),
            remaining=max(0, remaining),
            retry_after_seconds=max(0, retry_after),
            reset_after_seconds=max(1, reset_after),
        )

    def _key(self, subject_id: str, operation: OperationClass) -> str:
        subject_digest = hashlib.sha256(subject_id.encode("utf-8")).hexdigest()[:32]
        return f"{self._namespace}:{subject_digest}:{operation.value}"


class EmergencyReadRateLimiter:
    """Small process-local cap used only when Redis read admission is unavailable."""

    def __init__(self, *, capacity: int = 10, window_seconds: int = 60) -> None:
        if capacity <= 0 or window_seconds <= 0:
            raise ValueError("emergency rate-limit values must be positive")
        self._capacity = capacity
        self._window_seconds = window_seconds
        self._entries: dict[str, tuple[float, int]] = {}
        self._lock = asyncio.Lock()

    async def admit(self, subject_id: str, operation: OperationClass) -> RateLimitDecision:
        key = f"{subject_id}:{operation.value}"
        now = time.monotonic()
        async with self._lock:
            started, count = self._entries.get(key, (now, 0))
            if now - started >= self._window_seconds:
                started, count = now, 0
            allowed = count < self._capacity
            if allowed:
                count += 1
            self._entries[key] = (started, count)
            retry_after = max(1, math.ceil(self._window_seconds - (now - started)))
            return RateLimitDecision(
                allowed=allowed,
                remaining=max(0, self._capacity - count),
                retry_after_seconds=0 if allowed else retry_after,
                reset_after_seconds=retry_after,
            )


HIGH_RISK_OPERATIONS = frozenset(
    {
        OperationClass.DISPATCH_SUBMIT,
        OperationClass.RUNTIME_OVERRIDE,
        OperationClass.MEMORY_MUTATION,
        OperationClass.WS_TICKET,
    }
)


class RateLimitAdmission:
    def __init__(
        self,
        limiter: RateLimiter,
        policies: dict[OperationClass, RateLimitPolicy],
        *,
        emergency_reads: RateLimiter | None = None,
    ) -> None:
        self._limiter = limiter
        self._policies = dict(policies)
        self._emergency_reads = emergency_reads or EmergencyReadRateLimiter()

    async def check(
        self,
        principal: AuthenticatedPrincipal,
        operation: OperationClass,
    ) -> RateLimitDecision:
        try:
            decision = await self._limiter.admit(principal.subject_id, operation)
        except RateLimiterUnavailable:
            if operation in HIGH_RISK_OPERATIONS:
                raise SecurityHttpError(
                    503,
                    "SECURITY_CONTROL_UNAVAILABLE",
                    "Security admission is temporarily unavailable.",
                ) from None
            decision = await self._emergency_reads.admit(principal.subject_id, operation)
        if not decision.allowed:
            policy = self._policies[operation]
            raise SecurityHttpError(
                429,
                "RATE_LIMIT_EXCEEDED",
                "The operation rate limit has been exceeded.",
                {
                    "Retry-After": str(max(1, decision.retry_after_seconds)),
                    "X-RateLimit-Limit": str(policy.capacity),
                    "X-RateLimit-Remaining": str(decision.remaining),
                    "X-RateLimit-Reset": str(decision.reset_after_seconds),
                },
            )
        return decision


def require_rate_limit(operation: OperationClass):
    async def dependency(
        request: Request,
        principal: PrincipalDependency,
    ) -> RateLimitDecision:
        try:
            return await request.app.state.rate_limit_admission.check(principal, operation)
        except SecurityHttpError as error:
            record_security_metric(
                getattr(request.app.state, "metrics_recorder", None),
                "countyflow_rate_limit_exceeded_total",
                reason_code="limit" if error.code == "RATE_LIMIT_EXCEEDED" else "control_unavailable",
                path=request.url.path,
            )
            recorder = getattr(request.app.state, "security_audit_recorder", None)
            if recorder is not None:
                try:
                    recorder.record(
                        request,
                        event_type=SecurityAuditEventType.RATE_LIMIT_EXCEEDED,
                        status=SecurityAuditStatus.DENIED,
                        reason_code=error.code,
                        principal=principal,
                        permission=None,
                    )
                except SecurityAuditUnavailable:
                    pass
            raise

    return dependency


def policies_from_settings(settings) -> dict[OperationClass, RateLimitPolicy]:
    return {
        OperationClass.DISPATCH_SUBMIT: RateLimitPolicy(
            settings.rate_limit_dispatch_submit_capacity,
            settings.rate_limit_dispatch_submit_refill_per_minute,
        ),
        OperationClass.RUNTIME_OVERRIDE: RateLimitPolicy(
            settings.rate_limit_runtime_override_capacity,
            settings.rate_limit_runtime_override_refill_per_minute,
        ),
        OperationClass.MEMORY_MUTATION: RateLimitPolicy(
            settings.rate_limit_memory_mutation_capacity,
            settings.rate_limit_memory_mutation_refill_per_minute,
        ),
        OperationClass.OBSERVABILITY_READ: RateLimitPolicy(
            settings.rate_limit_observability_read_capacity,
            settings.rate_limit_observability_read_refill_per_minute,
        ),
        OperationClass.WS_TICKET: RateLimitPolicy(
            settings.rate_limit_ws_ticket_capacity,
            settings.rate_limit_ws_ticket_refill_per_minute,
        ),
        OperationClass.AUTHENTICATION_INVALID: RateLimitPolicy(
            settings.rate_limit_authentication_invalid_capacity,
            settings.rate_limit_authentication_invalid_refill_per_minute,
        ),
    }
