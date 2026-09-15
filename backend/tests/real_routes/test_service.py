import pytest

from app.providers.errors import ProviderTimeout
from app.real_routes.service import RealRoadRouteService


class FailingProvider:
    async def plan(self, origin, destination, waypoints):
        raise ProviderTimeout("provider details must stay internal")


@pytest.mark.asyncio
async def test_missing_provider_returns_client_waypoint_fallback() -> None:
    result = await RealRoadRouteService(None).plan(("N01", "N03", "N11"))

    assert result.provider == "AMAP"
    assert result.source == "CLIENT_WAYPOINT_FALLBACK"
    assert result.status == "CLIENT_MATCH_REQUIRED"
    assert result.coordinate_system == "GCJ02"
    assert result.mapping_version == "DEMO_AMAP_V1"
    assert [point.node_id for point in result.waypoints] == ["N01", "N03", "N11"]
    assert result.polyline == result.waypoints
    assert result.fallback_reason == "AMap Web Service is not configured."


@pytest.mark.asyncio
async def test_provider_failure_returns_safe_client_waypoint_fallback() -> None:
    result = await RealRoadRouteService(FailingProvider()).plan(("N01", "N06"))

    assert result.status == "CLIENT_MATCH_REQUIRED"
    assert result.source == "CLIENT_WAYPOINT_FALLBACK"
    assert result.fallback_reason == "AMap Web Service is temporarily unavailable."
    assert "provider details" not in result.fallback_reason
