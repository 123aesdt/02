from decimal import Decimal

import httpx
import pytest

from app.providers.errors import ProviderResponseError
from app.real_routes.amap_provider import AmapDrivingRouteProvider
from app.real_routes.demo_coordinates import demo_geo_point
from app.real_routes.models import GeoPoint


def test_demo_node_coordinates_are_stable_gcj02_points() -> None:
    assert demo_geo_point("N01") == GeoPoint(
        node_id="N01",
        longitude=Decimal("103.044800"),
        latitude=Decimal("25.226500"),
    )


@pytest.mark.asyncio
async def test_amap_provider_selects_fastest_valid_candidate_and_parses_polyline() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "status": "1",
                "route": {
                    "paths": [
                        {
                            "distance": "6000",
                            "cost": {"duration": "900"},
                            "steps": [{"polyline": "103.044800,25.226500;103.050000,25.230000"}],
                        },
                        {
                            "distance": "7200",
                            "cost": {"duration": "720"},
                            "steps": [
                                {"polyline": "103.044800,25.226500;103.060000,25.235000"},
                                {"polyline": "103.060000,25.235000;103.079000,25.246000"},
                            ],
                        },
                    ]
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = AmapDrivingRouteProvider(
            "server-secret-key",
            client=client,
            timeout_seconds=0.8,
        )
        result = await provider.plan(
            GeoPoint("N01", Decimal("103.044800"), Decimal("25.226500")),
            GeoPoint("N04", Decimal("103.079000"), Decimal("25.246000")),
            (GeoPoint("N03", Decimal("103.057000"), Decimal("25.239000")),),
        )

    assert result.distance_meters == 7200
    assert result.duration_seconds == 720
    assert result.polyline == (
        GeoPoint(None, Decimal("103.044800"), Decimal("25.226500")),
        GeoPoint(None, Decimal("103.060000"), Decimal("25.235000")),
        GeoPoint(None, Decimal("103.079000"), Decimal("25.246000")),
    )
    assert requests[0].url.params["origin"] == "103.044800,25.226500"
    assert requests[0].url.params["destination"] == "103.079000,25.246000"
    assert requests[0].url.params["waypoints"] == "103.057000,25.239000"
    assert requests[0].url.params["alternative_route"] == "2"


@pytest.mark.asyncio
async def test_amap_provider_normalizes_invalid_response_without_exposing_key() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"status": "0", "info": "INVALID_USER_KEY"})
        )
    ) as client:
        provider = AmapDrivingRouteProvider(
            "do-not-leak-this-key",
            client=client,
            timeout_seconds=0.8,
        )
        with pytest.raises(ProviderResponseError) as raised:
            await provider.plan(
                demo_geo_point("N01"),
                demo_geo_point("N06"),
                (),
            )

    assert str(raised.value) == "AMap route provider response invalid"
    assert "do-not-leak-this-key" not in str(raised.value)
