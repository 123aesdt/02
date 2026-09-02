from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Protocol
from uuid import uuid4

from redis.exceptions import RedisError

THREAD_LOCK_KEY_PREFIX = "countyflow:lock:thread:"


class RuntimeBoundaryLockClient(Protocol):
    async def set(self, name: str, value: str, *, nx: bool, px: int) -> bool | None: ...

    async def transaction(
        self,
        func: Callable[[object], Awaitable[bool]],
        *watches: str,
        **kwargs: object,
    ) -> bool: ...


class RuntimeBoundaryLockError(Exception):
    """Normalized Redis boundary-lock failure without connection details."""


@dataclass(frozen=True)
class RuntimeBoundaryLockHandle:
    key: str
    token: str
    acquired: bool

    def with_token(self, token: str) -> "RuntimeBoundaryLockHandle":
        return replace(self, token=token)


class RuntimeBoundaryLock:
    def __init__(self, client: RuntimeBoundaryLockClient, *, ttl_ms: int) -> None:
        if ttl_ms <= 0:
            raise ValueError("runtime boundary lock ttl_ms must be positive")
        self._client = client
        self._ttl_ms = ttl_ms

    async def acquire(self, thread_id: str) -> RuntimeBoundaryLockHandle:
        key = f"{THREAD_LOCK_KEY_PREFIX}{thread_id}"
        token = uuid4().hex
        try:
            acquired = await self._client.set(key, token, nx=True, px=self._ttl_ms)
        except RedisError as error:
            raise RuntimeBoundaryLockError("Redis runtime boundary lock acquire failed") from error
        return RuntimeBoundaryLockHandle(
            key=key,
            token=token,
            acquired=acquired is True or acquired == b"OK",
        )

    async def release(self, handle: RuntimeBoundaryLockHandle) -> bool:
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
            released = await self._client.transaction(
                compare_and_delete,
                handle.key,
                value_from_callable=True,
            )
        except RedisError as error:
            raise RuntimeBoundaryLockError("Redis runtime boundary lock release failed") from error
        return released is True
