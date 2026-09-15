from decimal import Decimal

import pytest

from app.capacity.provider import FleetCapacityProvider
from app.fleet.models import FleetDriverSnapshot, FleetVehicleSnapshot


class _FleetProvider:
    def __init__(self, vehicle: FleetVehicleSnapshot) -> None:
        self._vehicle = vehicle

    def get_vehicle(self, vehicle_id: str) -> FleetVehicleSnapshot | None:
        return self._vehicle if vehicle_id == self._vehicle.vehicle_id else None


def _vehicle(status: str) -> FleetVehicleSnapshot:
    return FleetVehicleSnapshot(
        vehicle_id="V-002",
        plate_no="新物厢货-02",
        vehicle_type="VAN",
        max_load_kg=Decimal("1200.00"),
        current_load_kg=Decimal("200.00"),
        cargo_capability="GENERAL",
        gross_weight_tons=Decimal("2.20"),
        status=status,
        current_node_id="N01",
        driver=FleetDriverSnapshot("D-002", "张师傅", "C1", "ON_DUTY", "N01"),
    )


@pytest.mark.asyncio
async def test_current_in_transit_vehicle_remains_available_for_road_rerouting() -> None:
    snapshot = await FleetCapacityProvider(_FleetProvider(_vehicle("IN_TRANSIT"))).get_capacity(
        "D-002",
        "V-002",
        "ROUTE-01",
        25,
    )

    assert snapshot.driver_available is True
    assert snapshot.vehicle_available is True


@pytest.mark.asyncio
async def test_faulted_vehicle_remains_unavailable() -> None:
    snapshot = await FleetCapacityProvider(_FleetProvider(_vehicle("BROKEN"))).get_capacity(
        "D-002",
        "V-002",
        "ROUTE-01",
        25,
    )

    assert snapshot.vehicle_available is False
