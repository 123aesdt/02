import pytest

from app.services.circuit_breaker import CircuitBreaker, CircuitState


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


@pytest.mark.asyncio
async def test_circuit_breaker_starts_closed():
    breaker = CircuitBreaker(3, 5.0)

    assert await breaker.current_state() is CircuitState.CLOSED
    assert await breaker.allow_request() is True


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold():
    breaker = CircuitBreaker(3, 5.0)

    for _ in range(3):
        await breaker.record_failure()

    assert await breaker.current_state() is CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_rejects_while_open():
    breaker = CircuitBreaker(1, 5.0)
    await breaker.record_failure()

    assert await breaker.allow_request() is False


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_recovery():
    clock = _Clock()
    breaker = CircuitBreaker(1, 5.0, clock=clock)
    await breaker.record_failure()
    clock.value = 5.0

    assert await breaker.allow_request() is True
    assert await breaker.current_state() is CircuitState.HALF_OPEN
    await breaker.record_success()

    assert await breaker.current_state() is CircuitState.CLOSED
    assert breaker.failure_count == 0
