import time

from app.providers.environment import EnvironmentProvider, EnvironmentResult, StaticRouteFallbackProvider
from app.providers.errors import ProviderError, ProviderTimeout
from app.services.circuit_breaker import CircuitBreaker


class EnvironmentService:
    def __init__(
        self,
        primary_provider: EnvironmentProvider,
        fallback_provider: StaticRouteFallbackProvider,
        circuit_breaker: CircuitBreaker,
    ) -> None:
        self._primary_provider = primary_provider
        self._fallback_provider = fallback_provider
        self._circuit_breaker = circuit_breaker

    async def get_environment(self, route_id: str) -> EnvironmentResult:
        started_at = time.perf_counter()
        if not await self._circuit_breaker.allow_request():
            return await self._fallback_provider.get_fallback(
                route_id,
                "Environment circuit breaker is open.",
                (time.perf_counter() - started_at) * 1000,
            )
        try:
            result = await self._primary_provider.get_environment(route_id)
        except ProviderError as error:
            await self._circuit_breaker.record_failure()
            reason = "Primary environment provider timed out." if isinstance(error, ProviderTimeout) else "Primary environment provider failed."
            return await self._fallback_provider.get_fallback(route_id, reason, (time.perf_counter() - started_at) * 1000)
        await self._circuit_breaker.record_success()
        return result
