import asyncio
import time
from collections.abc import Callable
from enum import StrEnum


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int, recovery_seconds: float, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._clock = clock
        self._lock = asyncio.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None
        self._half_open_probe_in_flight = False

    @property
    def failure_count(self) -> int:
        return self._failure_count

    async def current_state(self) -> CircuitState:
        async with self._lock:
            return self._state

    async def allow_request(self) -> bool:
        async with self._lock:
            if self._state is CircuitState.CLOSED:
                return True
            if self._state is CircuitState.OPEN:
                if self._opened_at is None or self._clock() - self._opened_at < self._recovery_seconds:
                    return False
                self._state = CircuitState.HALF_OPEN
                self._half_open_probe_in_flight = True
                return True
            if self._half_open_probe_in_flight:
                return False
            self._half_open_probe_in_flight = True
            return True

    async def record_success(self) -> None:
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at = None
            self._half_open_probe_in_flight = False

    async def record_failure(self) -> None:
        async with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._open()
                return
            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._open()

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()
        self._half_open_probe_in_flight = False
