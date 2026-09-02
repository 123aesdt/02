from typing import Protocol

from app.capacity.models import CapacitySnapshot


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
