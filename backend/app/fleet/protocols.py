from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.fleet.models import FleetVehicleSnapshot
from app.road_network.models import PathResult, RoadNetworkSnapshot


class FleetProvider(Protocol):
    def list_candidates(self, excluding_vehicle_id: str) -> tuple[FleetVehicleSnapshot, ...]: ...


class TravelTimeEstimator(Protocol):
    def estimate(self, from_node_id: str, to_node_id: str, vehicle_weight_tons: Decimal) -> PathResult | None: ...


@runtime_checkable
class AllocationPreparableTravelTimeEstimator(Protocol):
    def for_allocation(self) -> TravelTimeEstimator: ...


@runtime_checkable
class SnapshotPreparableTravelTimeEstimator(Protocol):
    def for_snapshot(self, snapshot: RoadNetworkSnapshot) -> TravelTimeEstimator: ...
