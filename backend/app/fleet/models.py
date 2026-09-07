from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.road_network.models import PathResult

_LOAD_QUANTUM = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class FleetDriverSnapshot:
    driver_id: str
    name: str
    license_class: str
    status: str
    current_node_id: str


@dataclass(frozen=True, slots=True)
class FleetVehicleSnapshot:
    vehicle_id: str
    plate_no: str
    vehicle_type: str
    max_load_kg: Decimal
    current_load_kg: Decimal
    cargo_capability: str
    gross_weight_tons: Decimal
    status: str
    current_node_id: str
    driver: FleetDriverSnapshot | None

    @property
    def remaining_load_kg(self) -> Decimal:
        return (self.max_load_kg - self.current_load_kg).quantize(_LOAD_QUANTUM, rounding=ROUND_HALF_UP)

    @property
    def current_load_ratio(self) -> Decimal:
        if self.max_load_kg == Decimal("0"):
            return Decimal("0")
        return self.current_load_kg / self.max_load_kg


@dataclass(frozen=True, slots=True)
class FleetAllocationRequest:
    original_vehicle_id: str
    incident_node_id: str
    cargo_weight_kg: Decimal
    cargo_type: str
    destination_node_id: str | None = None


@dataclass(frozen=True, slots=True)
class FleetScoreComponents:
    eta_penalty: Decimal
    distance_penalty: Decimal
    load_penalty: Decimal
    road_risk_penalty: Decimal
    same_station_bonus: Decimal
    cargo_exact_match_bonus: Decimal


@dataclass(frozen=True, slots=True)
class VehicleCandidate:
    vehicle_id: str
    driver_id: str | None
    vehicle_status: str
    remaining_load_kg: Decimal
    pickup_route: PathResult | None
    pickup_distance_km: Decimal | None
    pickup_eta_minutes: int | None
    score_components: FleetScoreComponents | None
    score: Decimal | None
    eligible: bool
    exclusion_reasons: tuple[str, ...]
    gross_weight_tons: Decimal = Decimal("0.00")
    cargo_capability: str = ""
    driver_status: str | None = None

@dataclass(frozen=True, slots=True)
class FleetAllocationResult:
    original_vehicle_id: str
    candidates: tuple[VehicleCandidate, ...]
    selected_vehicle_id: str | None
    selected_driver_id: str | None
    pickup_route: PathResult | None
    vehicle_reassigned: bool
    status: str
    reason: str | None
