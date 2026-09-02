from dataclasses import dataclass


@dataclass(frozen=True)
class CapacitySnapshot:
    driver_available: bool
    vehicle_available: bool
    load_ratio: float
    station_load_ratio: float | None
    provider_name: str


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
