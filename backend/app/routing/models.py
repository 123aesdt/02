from dataclasses import dataclass, field
from decimal import Decimal

from app.road_network.models import PathResult


@dataclass(frozen=True)
class RouteCandidate:
    route_id: str
    route_name: str
    distance_km: float
    estimated_minutes: int
    risk_level: str
    available: bool
    reason: str | None
    score: float
    node_ids: tuple[str, ...] = ()
    edge_ids: tuple[str, ...] = ()
    objective: str | None = None
    algorithm_version: str | None = None
    road_network_version: int | None = None
    visited_node_count: int | None = None
    risk_cost: Decimal | None = None
    scoring_formula: str | None = None


@dataclass(frozen=True)
class RoutingResult:
    candidate_routes: list[RouteCandidate]
    recommended_route: str | None
    decision: str
    decision_reason: str
    memory_adopted: bool
    adopted_memory_id: str | None
    routing_status: str
    requires_manual_review: bool
    original_path: PathResult | None = None
    recommended_path: PathResult | None = None
    blocked_edge_ids: tuple[str, ...] = ()
    road_network_version: int | None = None
    road_network_nodes: list[dict[str, object]] = field(default_factory=list)
    road_network_edges: list[dict[str, object]] = field(default_factory=list)
