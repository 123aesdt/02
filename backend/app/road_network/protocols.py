from decimal import Decimal
from typing import Protocol

from app.road_network.models import PathResult, RoadNetworkSnapshot, RouteObjective


class RoadNetworkProvider(Protocol):
    def snapshot(self) -> RoadNetworkSnapshot: ...


class PathFinder(Protocol):
    def find(
        self,
        snapshot: RoadNetworkSnapshot,
        start_node_id: str,
        end_node_id: str,
        objective: RouteObjective,
        vehicle_weight_tons: Decimal,
        excluded_edge_ids: frozenset[str] = frozenset(),
    ) -> PathResult | None: ...