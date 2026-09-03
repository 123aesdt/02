from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class RouteObjective(StrEnum):
    FASTEST = "FASTEST"
    SHORTEST = "SHORTEST"
    SAFEST = "SAFEST"


@dataclass(frozen=True)
class RoadNodeSnapshot:
    node_id: str
    name: str
    x_km: Decimal
    y_km: Decimal
    node_type: str


@dataclass(frozen=True)
class RoadEdgeSnapshot:
    edge_id: str
    name: str
    from_node_id: str
    to_node_id: str
    distance_km: Decimal
    base_minutes: int
    road_level: str
    risk_level: str
    status: str
    congestion_factor: Decimal
    weight_limit_tons: Decimal
    bidirectional: bool
    version: int


@dataclass(frozen=True)
class RoadNetworkSnapshot:
    version: int
    nodes: tuple[RoadNodeSnapshot, ...]
    edges: tuple[RoadEdgeSnapshot, ...]


@dataclass(frozen=True)
class PathResult:
    objective: RouteObjective
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    distance_km: Decimal
    estimated_minutes: int
    risk_cost: Decimal
    visited_node_count: int