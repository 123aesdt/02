import hashlib
import math
from datetime import UTC, datetime

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.security.protocols import AuthenticationProviderUnavailable


class RedisRevocationStore:
    def __init__(self, redis: Redis, namespace: str = "countyflow:auth:revoked") -> None:
        self._redis = redis
        self._namespace = namespace.rstrip(":")

    def _key(self, jti: str) -> str:
        digest = hashlib.sha256(jti.encode()).hexdigest()
        return f"{self._namespace}:{digest}"

    async def revoke(self, jti: str, expires_at: datetime) -> None:
        now = datetime.now(UTC)
        remaining = math.ceil((expires_at.astimezone(UTC) - now).total_seconds())
        if remaining <= 0:
            return
        try:
            await self._redis.set(self._key(jti), b"1", ex=remaining)
        except RedisError as error:
            raise AuthenticationProviderUnavailable from error

    async def is_revoked(self, jti: str) -> bool:
        try:
            return bool(await self._redis.exists(self._key(jti)))
        except RedisError as error:
            raise AuthenticationProviderUnavailable from error

