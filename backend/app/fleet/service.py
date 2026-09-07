from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol, runtime_checkable

from app.fleet.models import (
    FleetAllocationRequest,
    FleetAllocationResult,
    FleetScoreComponents,
    FleetVehicleSnapshot,
    VehicleCandidate,
)
from app.fleet.protocols import (
    AllocationPreparableTravelTimeEstimator,
    FleetProvider,
    SnapshotPreparableTravelTimeEstimator,
    TravelTimeEstimator,
)
from app.road_network.models import PathResult, RoadNetworkSnapshot, RouteObjective
from app.road_network.protocols import PathFinder, RoadNetworkProvider

_SCORE_QUANTUM = Decimal("0.1")
_RISK_PENALTIES = {"LOW": Decimal("0"), "MEDIUM": Decimal("6"), "HIGH": Decimal("15")}
_LIGHT_VEHICLE_TYPES = frozenset({"VAN", "REFRIGERATED_VAN", "ELECTRIC_VAN", "TRICYCLE"})


@runtime_checkable
class _WeightRestrictionAware(Protocol):
    def is_weight_restricted(self, from_node_id: str, to_node_id: str, vehicle_weight_tons: Decimal) -> bool: ...


class DijkstraTravelTimeEstimator:
    def __init__(self, road_network: RoadNetworkProvider, path_finder: PathFinder) -> None:
        self._road_network = road_network
        self._path_finder = path_finder

    def estimate(self, from_node_id: str, to_node_id: str, vehicle_weight_tons: Decimal) -> PathResult | None:
        snapshot = self._road_network.snapshot()
        return self._path_finder.find(snapshot, from_node_id, to_node_id, RouteObjective.FASTEST, vehicle_weight_tons)

    def is_weight_restricted(self, from_node_id: str, to_node_id: str, vehicle_weight_tons: Decimal) -> bool:
        return _is_weight_restricted(self._path_finder, self._road_network.snapshot(), from_node_id, to_node_id, vehicle_weight_tons)

    def for_allocation(self) -> TravelTimeEstimator:
        return self.for_snapshot(self._road_network.snapshot())

    def for_snapshot(self, snapshot: RoadNetworkSnapshot) -> TravelTimeEstimator:
        return _PreparedDijkstraTravelTimeEstimator(snapshot, self._path_finder)


class _PreparedDijkstraTravelTimeEstimator:
    def __init__(self, snapshot: RoadNetworkSnapshot, path_finder: PathFinder) -> None:
        self._snapshot = snapshot
        self._path_finder = path_finder

    def estimate(self, from_node_id: str, to_node_id: str, vehicle_weight_tons: Decimal) -> PathResult | None:
        return self._path_finder.find(self._snapshot, from_node_id, to_node_id, RouteObjective.FASTEST, vehicle_weight_tons)

    def is_weight_restricted(self, from_node_id: str, to_node_id: str, vehicle_weight_tons: Decimal) -> bool:
        return _is_weight_restricted(self._path_finder, self._snapshot, from_node_id, to_node_id, vehicle_weight_tons)


def _is_weight_restricted(
    path_finder: PathFinder,
    snapshot: RoadNetworkSnapshot,
    from_node_id: str,
    to_node_id: str,
    vehicle_weight_tons: Decimal,
) -> bool:
    return path_finder.find(snapshot, from_node_id, to_node_id, RouteObjective.FASTEST, vehicle_weight_tons) is None and (
        path_finder.find(snapshot, from_node_id, to_node_id, RouteObjective.FASTEST, Decimal("0")) is not None
    )


class FleetAllocationService:
    def __init__(self, fleet_provider: FleetProvider, travel_time_estimator: TravelTimeEstimator) -> None:
        self._fleet_provider = fleet_provider
        self._travel_time_estimator = travel_time_estimator

    def allocate(
        self,
        request: FleetAllocationRequest,
        *,
        road_network_snapshot: RoadNetworkSnapshot | None = None,
    ) -> FleetAllocationResult:
        estimator = self._prepare_estimator(road_network_snapshot)
        candidates = tuple(self._evaluate(vehicle, request, estimator) for vehicle in self._fleet_provider.list_candidates(request.original_vehicle_id))
        eligible = sorted(
            (candidate for candidate in candidates if candidate.eligible),
            key=lambda candidate: (-candidate.score, candidate.pickup_eta_minutes, candidate.vehicle_id),
        )
        rejected = sorted((candidate for candidate in candidates if not candidate.eligible), key=lambda candidate: candidate.vehicle_id)
        ordered = tuple((*eligible, *rejected))
        if not eligible:
            return FleetAllocationResult(request.original_vehicle_id, ordered, None, None, None, False, "UNAVAILABLE", "NO_REPLACEMENT_VEHICLE")
        selected = eligible[0]
        return FleetAllocationResult(
            request.original_vehicle_id,
            ordered,
            selected.vehicle_id,
            selected.driver_id,
            selected.pickup_route,
            True,
            "REASSIGNED",
            None,
        )

    def _evaluate(self, vehicle: FleetVehicleSnapshot, request: FleetAllocationRequest, estimator: TravelTimeEstimator) -> VehicleCandidate:
        reasons = self._cheap_reasons(vehicle, request)
        if reasons:
            return self._rejected(vehicle, reasons)
        pickup = estimator.estimate(vehicle.current_node_id, request.incident_node_id, vehicle.gross_weight_tons)
        if pickup is None:
            if self._weight_restricted(estimator, vehicle, vehicle.current_node_id, request.incident_node_id):
                reasons.append("ROAD_WEIGHT_RESTRICTION")
            reasons.append("PICKUP_UNREACHABLE")
            return self._rejected(vehicle, reasons)
        if request.destination_node_id is not None:
            delivery = estimator.estimate(request.incident_node_id, request.destination_node_id, vehicle.gross_weight_tons)
            if delivery is None:
                if self._weight_restricted(estimator, vehicle, request.incident_node_id, request.destination_node_id):
                    reasons.append("ROAD_WEIGHT_RESTRICTION")
                reasons.append("DELIVERY_UNREACHABLE")
                return self._rejected(vehicle, reasons, pickup)
        components = self._score_components(vehicle, request, pickup)
        score = (
            Decimal("100")
            - components.eta_penalty
            - components.distance_penalty
            - components.load_penalty
            - components.road_risk_penalty
            + components.same_station_bonus
            + components.cargo_exact_match_bonus
        ).quantize(_SCORE_QUANTUM, rounding=ROUND_HALF_UP)
        return VehicleCandidate(
            vehicle.vehicle_id,
            vehicle.driver.driver_id if vehicle.driver else None,
            vehicle.status,
            vehicle.remaining_load_kg,
            pickup,
            pickup.distance_km,
            pickup.estimated_minutes,
            components,
            score,
            True,
            (),
            vehicle.gross_weight_tons,
        )

    @staticmethod
    def _cheap_reasons(vehicle: FleetVehicleSnapshot, request: FleetAllocationRequest) -> list[str]:
        reasons: list[str] = []
        if vehicle.vehicle_id == request.original_vehicle_id:
            reasons.append("ORIGINAL_VEHICLE_EXCLUDED")
        if vehicle.status != "AVAILABLE":
            reasons.append("VEHICLE_UNAVAILABLE")
        if vehicle.driver is None:
            reasons.append("DRIVER_UNAVAILABLE")
        else:
            if vehicle.driver.status != "ON_DUTY":
                reasons.append("DRIVER_UNAVAILABLE")
            if not FleetAllocationService._license_matches(vehicle):
                reasons.append("LICENSE_MISMATCH")
        if vehicle.remaining_load_kg < request.cargo_weight_kg:
            reasons.append("INSUFFICIENT_CAPACITY")
        if request.cargo_type == "COLD_CHAIN" and vehicle.cargo_capability != "COLD_CHAIN":
            reasons.append("CARGO_CAPABILITY_MISMATCH")
        return reasons

    @staticmethod
    def _license_matches(vehicle: FleetVehicleSnapshot) -> bool:
        if vehicle.driver is None:
            return False
        return vehicle.driver.license_class in ({"C1", "B2"} if vehicle.vehicle_type in _LIGHT_VEHICLE_TYPES else {"B2"})

    def _prepare_estimator(self, road_network_snapshot: RoadNetworkSnapshot | None) -> TravelTimeEstimator:
        estimator = self._travel_time_estimator
        if road_network_snapshot is not None:
            if not isinstance(estimator, SnapshotPreparableTravelTimeEstimator):
                raise TypeError("Travel-time estimator does not accept an explicit road-network snapshot.")
            return estimator.for_snapshot(road_network_snapshot)
        if isinstance(estimator, AllocationPreparableTravelTimeEstimator):
            return estimator.for_allocation()
        return estimator

    def _weight_restricted(self, estimator: TravelTimeEstimator, vehicle: FleetVehicleSnapshot, from_node_id: str, to_node_id: str) -> bool:
        if not isinstance(estimator, _WeightRestrictionAware):
            return False
        return estimator.is_weight_restricted(from_node_id, to_node_id, vehicle.gross_weight_tons)

    @staticmethod
    def _score_components(vehicle: FleetVehicleSnapshot, request: FleetAllocationRequest, pickup: PathResult) -> FleetScoreComponents:
        return FleetScoreComponents(
            eta_penalty=Decimal(pickup.estimated_minutes) * Decimal("1.5"),
            distance_penalty=pickup.distance_km * Decimal("2"),
            load_penalty=vehicle.current_load_ratio * Decimal("20"),
            road_risk_penalty=_RISK_PENALTIES[_risk_level(pickup.risk_cost)],
            same_station_bonus=Decimal("8") if vehicle.current_node_id == request.incident_node_id else Decimal("0"),
            cargo_exact_match_bonus=Decimal("10") if vehicle.cargo_capability == request.cargo_type else Decimal("0"),
        )

    @staticmethod
    def _rejected(vehicle: FleetVehicleSnapshot, reasons: list[str], pickup: PathResult | None = None) -> VehicleCandidate:
        return VehicleCandidate(
            vehicle.vehicle_id,
            vehicle.driver.driver_id if vehicle.driver else None,
            vehicle.status,
            vehicle.remaining_load_kg,
            pickup,
            pickup.distance_km if pickup else None,
            pickup.estimated_minutes if pickup else None,
            None,
            None,
            False,
            tuple(reasons),
            vehicle.gross_weight_tons,
        )


def _risk_level(risk_cost: Decimal) -> str:
    if risk_cost >= Decimal("12"):
        return "HIGH"
    if risk_cost > Decimal("0"):
        return "MEDIUM"
    return "LOW"
