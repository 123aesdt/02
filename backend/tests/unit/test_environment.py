import asyncio

import pytest
from httpx import AsyncClient, MockTransport, Response

from app.providers.environment import (
    EnvironmentProvider,
    EnvironmentResult,
    HttpEnvironmentProvider,
    StaticRouteFallbackProvider,
)
from app.providers.errors import ProviderResponseError
from app.services.circuit_breaker import CircuitBreaker
from app.services.environment import EnvironmentService


class _FailingEnvironmentProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def get_environment(self, route_id: str) -> EnvironmentResult:
        self.calls += 1
        raise ProviderResponseError("unavailable")


@pytest.mark.asyncio
async def test_environment_provider_contract():
    fallback = StaticRouteFallbackProvider()

    result = await fallback.get_fallback("rain-route", "Primary environment provider timed out.", 12.0)

    assert isinstance(fallback, EnvironmentProvider)
    assert isinstance(result, EnvironmentResult)


@pytest.mark.asyncio
async def test_environment_http_success():
    async def handler(request):
        assert request.url.path == "/environment"
        assert request.url.params["route_id"] == "route-001"
        return Response(200, json={"weather": "clear", "road_condition": "dry", "risk_level": "low"})

    async with AsyncClient(transport=MockTransport(handler)) as client:
        provider = HttpEnvironmentProvider("https://environment.test", client=client, timeout_seconds=0.8)
        result = await EnvironmentService(provider, StaticRouteFallbackProvider(), CircuitBreaker(3, 5.0)).get_environment("route-001")

    assert result.weather == "clear"
    assert result.road_condition == "dry"
    assert result.risk_level == "low"
    assert result.provider_name == "http_environment"
    assert result.fallback_used is False
    assert result.fallback_reason is None


@pytest.mark.asyncio
async def test_environment_timeout_fallback():
    async def handler(request):
        await asyncio.sleep(2.0)
        return Response(200, json={})

    async with AsyncClient(transport=MockTransport(handler)) as client:
        provider = HttpEnvironmentProvider("https://environment.test", client=client, timeout_seconds=0.8)
        result = await EnvironmentService(provider, StaticRouteFallbackProvider(), CircuitBreaker(3, 5.0)).get_environment("rain-route")

    assert result.fallback_used is True
    assert result.fallback_reason == "Primary environment provider timed out."
    assert result.weather == "heavy_rain"
    assert 600 <= result.elapsed_ms < 1000


@pytest.mark.asyncio
async def test_environment_http_error_fallback():
    async def handler(request):
        return Response(503, json={"error": "unavailable"})

    async with AsyncClient(transport=MockTransport(handler)) as client:
        provider = HttpEnvironmentProvider("https://environment.test", client=client, timeout_seconds=0.8)
        result = await EnvironmentService(provider, StaticRouteFallbackProvider(), CircuitBreaker(3, 5.0)).get_environment("closed-route")

    assert result.fallback_used is True
    assert result.fallback_reason == "Primary environment provider failed."
    assert (result.road_condition, result.risk_level) == ("closed", "critical")


@pytest.mark.asyncio
async def test_environment_result_mapping():
    async def handler(request):
        return Response(200, json={"weather": "cloudy", "road_condition": "wet", "risk_level": "moderate"})

    async with AsyncClient(transport=MockTransport(handler)) as client:
        result = await HttpEnvironmentProvider("https://environment.test", client=client, timeout_seconds=0.8).get_environment("route-002")

    assert result == EnvironmentResult("cloudy", "wet", "moderate", "http_environment", False, None, result.elapsed_ms)


@pytest.mark.asyncio
async def test_environment_fallback_records_reason():
    result = await StaticRouteFallbackProvider().get_fallback("unknown-route", "Primary environment provider failed.", 24.0)

    assert result.provider_name == "static_route_fallback"
    assert result.fallback_used is True
    assert result.fallback_reason == "Primary environment provider failed."
    assert result.elapsed_ms == 24.0


@pytest.mark.asyncio
async def test_environment_service_skips_primary_while_circuit_is_open():
    primary = _FailingEnvironmentProvider()
    service = EnvironmentService(primary, StaticRouteFallbackProvider(), CircuitBreaker(1, 5.0))

    await service.get_environment("unknown-route")
    result = await service.get_environment("unknown-route")

    assert primary.calls == 1
    assert result.fallback_reason == "Environment circuit breaker is open."
    assert result.elapsed_ms < 100
