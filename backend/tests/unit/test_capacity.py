import pytest

from app.capacity.models import CapacityResult, CapacitySnapshot
from app.capacity.provider import InMemoryCapacityProvider
from app.capacity.service import CapacityService


def _service(snapshot: CapacitySnapshot) -> CapacityService:
    return CapacityService(
        InMemoryCapacityProvider({("driver-li", "vehicle-001"): snapshot}),
        limited_threshold=0.8,
        unavailable_threshold=1.0,
    )


@pytest.mark.asyncio
async def test_capacity_result_model():
    result = CapacityResult(True, True, 0.45, 0.60, "AVAILABLE", "low", None, "in_memory_capacity")

    assert result.capacity_status == "AVAILABLE"
    assert result.station_load_ratio == 0.60


@pytest.mark.asyncio
async def test_capacity_service_available():
    result = await _service(CapacitySnapshot(True, True, 0.45, 0.60, "in_memory_capacity")).evaluate("driver-li", "vehicle-001", "xinping-road", 1)

    assert (result.capacity_status, result.risk_level, result.reason) == ("AVAILABLE", "low", None)


@pytest.mark.asyncio
async def test_capacity_service_driver_unavailable():
    result = await _service(CapacitySnapshot(False, True, 0.45, 0.60, "in_memory_capacity")).evaluate("driver-li", "vehicle-001", "xinping-road", 1)

    assert (result.capacity_status, result.reason) == ("UNAVAILABLE", "Assigned driver is unavailable.")


@pytest.mark.asyncio
async def test_capacity_service_vehicle_unavailable():
    result = await _service(CapacitySnapshot(True, False, 0.45, 0.60, "in_memory_capacity")).evaluate("driver-li", "vehicle-001", "xinping-road", 1)

    assert (result.capacity_status, result.reason) == ("UNAVAILABLE", "Assigned vehicle is unavailable.")


@pytest.mark.asyncio
async def test_capacity_service_overloaded():
    result = await _service(CapacitySnapshot(True, True, 1.0, 0.60, "in_memory_capacity")).evaluate("driver-li", "vehicle-001", "xinping-road", 1)

    assert (result.capacity_status, result.risk_level) == ("UNAVAILABLE", "high")


@pytest.mark.asyncio
async def test_capacity_service_limited():
    result = await _service(CapacitySnapshot(True, True, 0.85, 0.60, "in_memory_capacity")).evaluate("driver-li", "vehicle-001", "xinping-road", 1)

    assert (result.capacity_status, result.reason) == ("LIMITED", "Vehicle load is approaching capacity.")


@pytest.mark.asyncio
@pytest.mark.parametrize("vehicle_status", ["BROKEN", "UNAVAILABLE", "MAINTENANCE"])
async def test_broken_vehicle_excluded_by_capacity(vehicle_status: str):
    result = await _service(
        CapacitySnapshot(True, True, 0.45, 0.60, "in_memory_capacity")
    ).evaluate(
        "driver-li",
        "vehicle-001",
        "xinping-road",
        1,
        vehicle_status=vehicle_status,
    )

    assert (result.vehicle_available, result.capacity_status) == (False, "UNAVAILABLE")
