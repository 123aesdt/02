from dataclasses import replace
from decimal import Decimal

from app.capacity.models import CapacityResult, CapacitySnapshot
from app.capacity.provider import CapacityProvider, CapacityProviderError


class CapacityEvaluationError(Exception):
    pass


class CapacityService:
    def __init__(self, provider: CapacityProvider, *, limited_threshold: float, unavailable_threshold: float) -> None:
        self._provider = provider
        self._limited_threshold = limited_threshold
        self._unavailable_threshold = unavailable_threshold

    async def evaluate(
        self,
        driver_id: str,
        vehicle_id: str | None,
        route_id: str,
        order_id: int,
        *,
        vehicle_status: str = "NORMAL",
        cargo_weight_kg: Decimal | None = None,
        cargo_type: str | None = None,
    ) -> CapacityResult:
        try:
            snapshot = await self._provider.get_capacity(driver_id, vehicle_id, route_id, order_id)
        except CapacityProviderError as error:
            raise CapacityEvaluationError("Capacity evaluation is temporarily unavailable.") from error
        if vehicle_status in {"BROKEN", "UNAVAILABLE", "MAINTENANCE"}:
            unavailable = replace(snapshot, vehicle_available=False)
            return self._result(
                unavailable,
                "UNAVAILABLE",
                "high",
                f"Vehicle runtime status is {vehicle_status}.",
            )
        if not snapshot.driver_available:
            return self._result(snapshot, "UNAVAILABLE", "high", "Assigned driver is unavailable.")
        if not snapshot.vehicle_available:
            return self._result(snapshot, "UNAVAILABLE", "high", "Assigned vehicle is unavailable.")
        if cargo_weight_kg is not None and snapshot.remaining_load_kg is not None and snapshot.remaining_load_kg < cargo_weight_kg:
            return self._result(snapshot, "UNAVAILABLE", "high", "Assigned vehicle has insufficient remaining payload.")
        if cargo_type == "COLD_CHAIN" and snapshot.cargo_capability is not None and snapshot.cargo_capability != "COLD_CHAIN":
            return self._result(snapshot, "UNAVAILABLE", "high", "Assigned vehicle lacks the required cargo capability.")
        if self._is_unavailable(snapshot.load_ratio, snapshot.station_load_ratio):
            return self._result(snapshot, "UNAVAILABLE", "high", "Vehicle or station load exceeds capacity.")
        if self._is_limited(snapshot.load_ratio, snapshot.station_load_ratio):
            return self._result(snapshot, "LIMITED", "medium", "Vehicle load is approaching capacity.")
        return self._result(snapshot, "AVAILABLE", "low", None)

    def _is_unavailable(self, load_ratio: float, station_load_ratio: float | None) -> bool:
        return load_ratio >= self._unavailable_threshold or (station_load_ratio is not None and station_load_ratio >= self._unavailable_threshold)

    def _is_limited(self, load_ratio: float, station_load_ratio: float | None) -> bool:
        return load_ratio >= self._limited_threshold or (station_load_ratio is not None and station_load_ratio >= self._limited_threshold)

    @staticmethod
    def _result(snapshot: CapacitySnapshot, capacity_status: str, risk_level: str, reason: str | None) -> CapacityResult:
        return CapacityResult(
            snapshot.driver_available,
            snapshot.vehicle_available,
            snapshot.load_ratio,
            snapshot.station_load_ratio,
            capacity_status,
            risk_level,
            reason,
            snapshot.provider_name,
        )
