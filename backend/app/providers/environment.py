import asyncio
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import httpx

from app.providers.errors import ProviderResponseError, ProviderTimeout


@dataclass(frozen=True)
class EnvironmentResult:
    weather: str
    road_condition: str
    risk_level: str
    provider_name: str
    fallback_used: bool
    fallback_reason: str | None
    elapsed_ms: float


@runtime_checkable
class EnvironmentProvider(Protocol):
    async def get_environment(self, route_id: str) -> EnvironmentResult: ...


class HttpEnvironmentProvider:
    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds))

    async def get_environment(self, route_id: str) -> EnvironmentResult:
        started_at = time.perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._client.get(
                    f"{self._base_url}/environment",
                    params={"route_id": route_id},
                    timeout=self._timeout_seconds,
                )
            response.raise_for_status()
            payload = response.json()
            return EnvironmentResult(
                weather=payload["weather"],
                road_condition=payload["road_condition"],
                risk_level=payload["risk_level"],
                provider_name="http_environment",
                fallback_used=False,
                fallback_reason=None,
                elapsed_ms=(time.perf_counter() - started_at) * 1000,
            )
        except (TimeoutError, httpx.TimeoutException) as error:
            raise ProviderTimeout("Environment request timed out") from error
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ProviderResponseError("Environment provider response invalid") from error

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class StaticRouteFallbackProvider:
    async def get_environment(self, route_id: str) -> EnvironmentResult:
        return await self.get_fallback(route_id, "Static route fallback selected.", 0.0)

    async def get_fallback(self, route_id: str, reason: str, elapsed_ms: float) -> EnvironmentResult:
        route_context = route_id.lower()
        if "closed" in route_context:
            weather, road_condition, risk_level = "unknown", "closed", "critical"
        elif "rain" in route_context or "slippery" in route_context:
            weather, road_condition, risk_level = "heavy_rain", "slippery", "high"
        else:
            weather, road_condition, risk_level = "unknown", "unknown", "elevated"
        return EnvironmentResult(
            weather=weather,
            road_condition=road_condition,
            risk_level=risk_level,
            provider_name="static_route_fallback",
            fallback_used=True,
            fallback_reason=reason,
            elapsed_ms=elapsed_ms,
        )
