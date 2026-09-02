from dataclasses import dataclass


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
