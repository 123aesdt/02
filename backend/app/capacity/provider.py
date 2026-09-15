from typing import Protocol

from app.capacity.models import CapacitySnapshot
from app.fleet.models import FleetVehicleSnapshot


class CapacityProviderError(Exception):
    pass


class CapacityProvider(Protocol):
    async def get_capacity(
        self,
        driver_id: str,
        vehicle_id: str | None,
        route_id: str,
        order_id: int,
    ) -> CapacitySnapshot: ...


class FleetVehicleSnapshotProvider(Protocol):
    def get_vehicle(self, vehicle_id: str) -> FleetVehicleSnapshot | None: ...


class FleetCapacityProvider:
    """Adapts detached fleet snapshots to the capacity application boundary."""

    def __init__(self, fleet_provider: FleetVehicleSnapshotProvider) -> None:
        self._fleet_provider = fleet_provider

    async def get_capacity(
        self,
        driver_id: str,
        vehicle_id: str | None,
        route_id: str,
        order_id: int,
    ) -> CapacitySnapshot:
        if vehicle_id is None:
            return CapacitySnapshot(False, False, 0.0, None, "sqlalchemy_fleet")
        vehicle = self._fleet_provider.get_vehicle(vehicle_id)
        if vehicle is None:
            return CapacitySnapshot(False, False, 0.0, None, "sqlalchemy_fleet")
        driver = vehicle.driver
        return CapacitySnapshot(
            driver_available=driver is not None and driver.driver_id == driver_id and driver.status == "ON_DUTY",
            vehicle_available=vehicle.status in {"AVAILABLE", "IN_TRANSIT"},
            load_ratio=float(vehicle.current_load_ratio),
            station_load_ratio=None,
            provider_name="sqlalchemy_fleet",
            remaining_load_kg=vehicle.remaining_load_kg,
            cargo_capability=vehicle.cargo_capability,
        )


class InMemoryCapacityProvider:
    def __init__(self, records: dict[tuple[str, str], CapacitySnapshot]) -> None:
        self._records = records

    async def get_capacity(
        self,
        driver_id: str,
        vehicle_id: str | None,
        route_id: str,
        order_id: int,
    ) -> CapacitySnapshot:
        if vehicle_id is None:
            return CapacitySnapshot(False, False, 0.0, None, "in_memory_capacity")
        return self._records.get(
            (driver_id, vehicle_id),
            CapacitySnapshot(False, False, 0.0, None, "in_memory_capacity"),
        )
