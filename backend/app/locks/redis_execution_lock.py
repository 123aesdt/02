from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Protocol
from uuid import uuid4

from redis.exceptions import RedisError

LOCK_KEY_PREFIX = "countyflow:lock:dispatch:"
class RedisExecutionLockClient(Protocol):
    async def set(self, name: str, value: str, *, nx: bool, px: int) -> bool | None: ...

    async def transaction(
        self,
        func: Callable[[object], Awaitable[bool]],
        *watches: str,
    ) -> bool: ...


class ExecutionLockError(Exception):
    """Raised when the Redis execution-lock boundary cannot complete an operation."""


@dataclass(frozen=True)
class LockHandle:
    key: str
    token: str
    acquired: bool

    def with_token(self, token: str) -> "LockHandle":
        return replace(self, token=token)


class RedisExecutionLock:
    def __init__(self, client: RedisExecutionLockClient, *, ttl_ms: int) -> None:
        self._client = client
        self._ttl_ms = ttl_ms

    async def acquire(self, idempotency_key: str) -> LockHandle:
        key = f"{LOCK_KEY_PREFIX}{idempotency_key}"
        token = uuid4().hex
        try:
            acquired = await self._client.set(key, token, nx=True, px=self._ttl_ms)
        except RedisError as error:
            raise ExecutionLockError("Redis execution lock acquire failed.") from error
        return LockHandle(key, token, acquired is True or acquired == b"OK")

    async def release(self, handle: LockHandle) -> bool:
        if not handle.acquired:
            return False

        async def compare_and_delete(pipe: object) -> bool:
            value = await pipe.get(handle.key)
            if value != handle.token.encode():
                return False
            pipe.multi()
            pipe.delete(handle.key)
            return True

        try:
            deleted = await self._client.transaction(compare_and_delete, handle.key, value_from_callable=True)
        except RedisError as error:
            raise ExecutionLockError("Redis execution lock release failed.") from error
        return deleted is True
