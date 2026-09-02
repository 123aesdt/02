import pytest

from app.graph.state import CapacityState, MemoryRecallState
from app.routing.models import RouteCandidate
from app.routing.provider import InMemoryRouteProvider
from app.routing.service import RoutingService


def _service() -> RoutingService:
    return RoutingService(InMemoryRouteProvider.default_catalog(), memory_adoption_threshold=0.75)


def _memory(score: float = 0.9, resolution: str = "建议改走102国道") -> list[MemoryRecallState]:
    return [
        {
            "memory_id": "memory-rain-li",
            "similarity_score": score,
            "driver_id": "driver-li",
            "route_id": "xinping-road",
            "anomaly_type": "rain_slippery",
            "historical_resolution": resolution,
            "metadata": {},
        }
    ]


def _capacity(status: str = "AVAILABLE") -> CapacityState:
    return {
        "driver_available": True,
        "vehicle_available": True,
        "load_ratio": 0.45,
        "station_load_ratio": 0.60,
        "capacity_status": status,
        "risk_level": "low",
        "reason": None,
        "provider_name": "in_memory_capacity",
    }


@pytest.mark.asyncio
async def test_route_candidate_model():
    candidate = RouteCandidate("xinping-road", "新平路", 10.0, 20, "low", True, None, 80.0)

    assert candidate.route_name == "新平路"


@pytest.mark.asyncio
async def test_routing_service_normal_route():
    result = await _service().route("xinping-road", [], "clear", "dry", "low", _capacity())

    assert (result.recommended_route, result.decision, result.routing_status) == ("xinping-road", "KEEP_ROUTE", "ROUTED")


@pytest.mark.asyncio
async def test_routing_service_adopts_memory():
    result = await _service().route("xinping-road", _memory(), "heavy_rain", "slippery", "high", _capacity())

    assert result.recommended_route == "national-102"
    assert result.memory_adopted is True
    assert result.adopted_memory_id == "memory-rain-li"
    assert "memory-rain-li" in result.decision_reason


@pytest.mark.asyncio
async def test_routing_service_avoids_risky_route():
    result = await _service().route("xinping-road", _memory(0.20), "heavy_rain", "slippery", "high", _capacity())

    assert result.recommended_route == "national-102"
    assert result.memory_adopted is False
    assert result.candidate_routes[-1].route_id == "xinping-road"
    assert result.candidate_routes[-1].available is False


@pytest.mark.asyncio
async def test_routing_service_capacity_unavailable():
    result = await _service().route("xinping-road", _memory(), "clear", "dry", "low", _capacity("UNAVAILABLE"))

    assert (result.decision, result.requires_manual_review, result.recommended_route) == ("MANUAL_REVIEW", True, None)


@pytest.mark.asyncio
async def test_routing_service_does_not_adopt_unavailable_memory_route():
    result = await _service().route("xinping-road", _memory(), "heavy_rain", "slippery", "high", _capacity())
    closed = await _service().route("xinping-road", _memory(), "unknown", "closed", "critical", _capacity())

    assert result.memory_adopted is True
    assert closed.recommended_route != "xinping-road"
    assert closed.candidate_routes[-1].route_id == "xinping-road"
