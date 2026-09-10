from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CapacitySnapshot:
    driver_available: bool
    vehicle_available: bool
    load_ratio: float
    station_load_ratio: float | None
    provider_name: str
    remaining_load_kg: Decimal | None = None
    cargo_capability: str | None = None


@dataclass(frozen=True)
class CapacityResult:
    driver_available: bool
    vehicle_available: bool
    load_ratio: float
    station_load_ratio: float | None
    capacity_status: str
    risk_level: str
    reason: str | None
    provider_name: str
