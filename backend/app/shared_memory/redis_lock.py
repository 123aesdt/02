from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Protocol
from uuid import uuid4

from redis.exceptions import RedisError

MEMORY_LOCK_KEY_PREFIX = "countyflow:lock:memory:"


class MemoryMutationLockClient(Protocol):
    async def set(self, name: str, value: str, *, nx: bool, px: int) -> bool | None: ...

    async def transaction(
        self,
        func: Callable[[object], Awaitable[bool]],
        *watches: str,
        **kwargs: object,
    ) -> bool: ...


class MemoryMutationLockError(Exception):
    """Normalized Redis fact-lock failure without provider details."""


@dataclass(frozen=True)
class MemoryLockHandle:
    key: str
    token: str
    acquired: bool

    def with_token(self, token: str) -> "MemoryLockHandle":
        return replace(self, token=token)


class MemoryMutationLock:
    def __init__(self, client: MemoryMutationLockClient, *, ttl_ms: int) -> None:
        if ttl_ms <= 0:
            raise ValueError("memory mutation lock ttl_ms must be positive")
        self._client = client
        self._ttl_ms = ttl_ms

    async def acquire(self, fact_key: str) -> MemoryLockHandle:
        key = f"{MEMORY_LOCK_KEY_PREFIX}{fact_key}"
        token = uuid4().hex
        try:
            acquired = await self._client.set(key, token, nx=True, px=self._ttl_ms)
        except RedisError as error:
            raise MemoryMutationLockError("Redis memory mutation lock acquire failed") from error
        return MemoryLockHandle(key=key, token=token, acquired=acquired is True or acquired == b"OK")

    async def release(self, handle: MemoryLockHandle) -> bool:
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
            deleted = await self._client.transaction(
                compare_and_delete,
                handle.key,
                value_from_callable=True,
            )
        except RedisError as error:
            raise MemoryMutationLockError("Redis memory mutation lock release failed") from error
        return deleted is True

