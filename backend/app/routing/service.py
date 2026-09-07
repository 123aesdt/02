from dataclasses import replace
from decimal import Decimal
from hashlib import sha256

from app.graph.state import CapacityState, MemoryRecallState
from app.road_network.models import PathResult, RoadNetworkSnapshot, RouteObjective
from app.road_network.protocols import PathFinder, RoadNetworkProvider
from app.routing.models import RouteCandidate, RouteScoreComponents, RoutingResult
from app.routing.provider import RouteProvider
from app.sandtable.models import SandtableTaskContext


class RoutingService:
    def __init__(
        self,
        route_provider: RouteProvider | None,
        *,
        memory_adoption_threshold: float,
        road_network_provider: RoadNetworkProvider | None = None,
        path_finder: PathFinder | None = None,
    ) -> None:
        self._route_provider = route_provider
        self._memory_adoption_threshold = memory_adoption_threshold
        self._road_network_provider = road_network_provider
        self._path_finder = path_finder

    @property
    def can_plan(self) -> bool:
        return self._road_network_provider is not None and self._path_finder is not None

    async def route(
        self,
        current_route_id: str,
        memory_results: list[MemoryRecallState],
        weather: str,
        road_condition: str,
        environment_risk: str,
        capacity_state: CapacityState,
    ) -> RoutingResult:
        capacity_status = capacity_state["capacity_status"]
        if capacity_status in {"UNAVAILABLE", "UNKNOWN"}:
            return RoutingResult(
                [], None, "MANUAL_REVIEW", f"Capacity status is {capacity_status}; manual review is required.", False, None, "MANUAL_REVIEW", True
            )
        if self._route_provider is None:
            return RoutingResult([], None, "MANUAL_REVIEW", "No route provider is configured.", False, None, "MANUAL_REVIEW", True)

        memory = memory_results[0] if memory_results else None
        memory_route = self._memory_route(memory)
        candidates = [
            self._score(candidate, current_route_id, road_condition, environment_risk, memory_route, capacity_status)
            for candidate in await self._route_provider.get_candidates()
        ]
        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        recommended = next((candidate for candidate in candidates if candidate.available), None)
        if recommended is None:
            return RoutingResult(candidates, None, "MANUAL_REVIEW", "No safe route is currently available.", False, None, "NO_SAFE_ROUTE", True)

        adopted = memory is not None and memory_route == recommended.route_id and recommended.available
        decision = "KEEP_ROUTE" if recommended.route_id == current_route_id else "REROUTE"
        reason = self._reason(recommended, road_condition, environment_risk, capacity_status, memory if adopted else None)
        return RoutingResult(candidates, recommended.route_id, decision, reason, adopted, memory["memory_id"] if adopted else None, "ROUTED", False)

    def plan(
        self,
        context: SandtableTaskContext,
        capacity_state: CapacityState,
        affected_edge_ids: list[str],
        memory_results: list[MemoryRecallState],
    ) -> RoutingResult:
        if not self.can_plan:
            return RoutingResult([], None, "MANUAL_REVIEW", "Road network planning is not configured.", False, None, "MANUAL_REVIEW", True)
        if capacity_state["capacity_status"] in {"UNAVAILABLE", "UNKNOWN"}:
            return RoutingResult([], None, "MANUAL_REVIEW", "No vehicle is available for route planning.", False, None, "MANUAL_REVIEW", True)

        snapshot = self._road_network_provider.snapshot()
        vehicle_weight_tons = context.vehicle_weight_tons
        start_node_id = context.incident_node_id or context.origin_node_id
        blocked = tuple(sorted(set(affected_edge_ids)))
        original_snapshot = RoadNetworkSnapshot(
            snapshot.version,
            snapshot.nodes,
            tuple(replace(edge, status="OPEN") if edge.edge_id in blocked else edge for edge in snapshot.edges),
        )
        original_path = self._path_finder.find(
            original_snapshot, context.origin_node_id, context.destination_node_id, RouteObjective.FASTEST, vehicle_weight_tons
        )
        paths = [
            path
            for objective in RouteObjective
            if (path := self._path_finder.find(snapshot, start_node_id, context.destination_node_id, objective, vehicle_weight_tons, frozenset(blocked)))
            is not None
        ]
        by_edges: dict[tuple[str, ...], PathResult] = {}
        for path in paths:
            by_edges.setdefault(path.edge_ids, path)
        if not by_edges:
            return RoutingResult(
                [],
                None,
                "MANUAL_REVIEW",
                "No reachable route remains after excluding affected roads.",
                False,
                None,
                "NO_REACHABLE_ROUTE",
                True,
                original_path=original_path,
                blocked_edge_ids=blocked,
                road_network_version=snapshot.version,
                road_network_nodes=self._nodes_to_state(snapshot),
                road_network_edges=self._edges_to_state(snapshot),
            )
        candidates = self._score_paths(list(by_edges.values()), snapshot.version)
        recommended = min(
            candidates,
            key=lambda candidate: (-candidate.score, candidate.estimated_minutes, candidate.distance_km, candidate.edge_ids),
        )
        recommended_path = by_edges[recommended.edge_ids]

        return RoutingResult(
            candidates,
            recommended.route_id,
            "REROUTE" if blocked or (original_path is not None and original_path.edge_ids != recommended_path.edge_ids) else "KEEP_ROUTE",
            "DIJKSTRA_V1 evaluated fastest, shortest, and safest paths using the fixed road-network snapshot.",
            False,
            None,
            "ROUTED",
            False,
            original_path=original_path,
            recommended_path=recommended_path,
            blocked_edge_ids=blocked,
            road_network_version=snapshot.version,
            road_network_nodes=self._nodes_to_state(snapshot),
            road_network_edges=self._edges_to_state(snapshot),
        )

    def _memory_route(self, memory: MemoryRecallState | None) -> str | None:
        if memory is None or memory["similarity_score"] < self._memory_adoption_threshold or self._route_provider is None:
            return None
        return self._route_provider.resolve_route_reference(memory["historical_resolution"])

    @staticmethod
    def _score(
        candidate: RouteCandidate,
        current_route_id: str,
        road_condition: str,
        environment_risk: str,
        memory_route: str | None,
        capacity_status: str,
    ) -> RouteCandidate:
        unsafe_current = candidate.route_id == current_route_id and road_condition in {"slippery", "closed"}
        if unsafe_current:
            return replace(
                candidate,
                risk_level="high" if road_condition == "slippery" else "critical",
                available=False,
                reason="Current route is unsafe for the reported road condition.",
                score=Decimal("-1000"),
            )
        score = Decimal("100") - candidate.distance_km * Decimal("2") - Decimal(candidate.estimated_minutes) * Decimal("0.1")
        if environment_risk in {"high", "critical"} and candidate.risk_level in {"medium", "high"}:
            score -= Decimal("15")
        if candidate.route_id == memory_route:
            score += Decimal("30")
        if capacity_status == "LIMITED":
            score -= Decimal("5")
        return replace(candidate, score=score)

    @staticmethod
    def _score_paths(paths: list[PathResult], road_network_version: int) -> list[RouteCandidate]:
        max_minutes = max(path.estimated_minutes for path in paths)
        max_distance = max(path.distance_km for path in paths)
        max_risk = max(path.risk_cost for path in paths)
        candidates: list[RouteCandidate] = []
        for path in paths:
            if len(paths) == 1:
                normalized_minutes = Decimal("0")
                normalized_distance = Decimal("0")
                normalized_risk = Decimal("0")
            else:
                normalized_minutes = Decimal(path.estimated_minutes) / Decimal(max_minutes)
                normalized_distance = path.distance_km / max_distance
                normalized_risk = Decimal("0") if max_risk == 0 else path.risk_cost / max_risk
            score_components = RouteScoreComponents(
                normalized_minutes=normalized_minutes,
                normalized_distance=normalized_distance,
                normalized_risk=normalized_risk,
                time_penalty=normalized_minutes * Decimal("45"),
                distance_penalty=normalized_distance * Decimal("30"),
                risk_penalty=normalized_risk * Decimal("25"),
            )
            score = Decimal("100") - score_components.time_penalty - score_components.distance_penalty - score_components.risk_penalty
            candidates.append(
                RouteCandidate(
                    route_id=f"RTE-{sha256('|'.join(path.edge_ids).encode()).hexdigest()[:16].upper()}",
                    route_name=f"{path.objective.value} route",
                    distance_km=path.distance_km,
                    estimated_minutes=path.estimated_minutes,
                    risk_level=RoutingService._risk_level(path.risk_cost),
                    available=True,
                    reason=None,
                    score=score,
                    node_ids=path.node_ids,
                    edge_ids=path.edge_ids,
                    objective=path.objective.value,
                    algorithm_version="DIJKSTRA_V1",
                    scoring_formula="ROUTE_SCORE_V1",
                    road_network_version=road_network_version,
                    visited_node_count=path.visited_node_count,
                    risk_cost=path.risk_cost,
                    score_components=score_components,
                )
            )
        return candidates

    @staticmethod
    def _risk_level(risk_cost: Decimal) -> str:
        if risk_cost >= Decimal("12"):
            return "high"
        if risk_cost > 0:
            return "medium"
        return "low"

    @staticmethod
    def _nodes_to_state(snapshot: RoadNetworkSnapshot) -> list[dict[str, object]]:
        return [
            {"node_id": node.node_id, "name": node.name, "x_km": str(node.x_km), "y_km": str(node.y_km), "node_type": node.node_type} for node in snapshot.nodes
        ]

    @staticmethod
    def _edges_to_state(snapshot: RoadNetworkSnapshot) -> list[dict[str, object]]:
        return [
            {
                "edge_id": edge.edge_id,
                "name": edge.name,
                "from_node_id": edge.from_node_id,
                "to_node_id": edge.to_node_id,
                "distance_km": str(edge.distance_km),
                "base_minutes": edge.base_minutes,
                "risk_level": edge.risk_level,
                "status": edge.status,
            }
            for edge in snapshot.edges
        ]

    @staticmethod
    def _reason(
        route: RouteCandidate,
        road_condition: str,
        environment_risk: str,
        capacity_status: str,
        memory: MemoryRecallState | None,
    ) -> str:
        base = f"Road condition is {road_condition} with {environment_risk} environmental risk; capacity status is {capacity_status}."
        if memory is None:
            return f"{base} Recommended {route.route_name} by deterministic safety and distance score."
        return (
            f"{base} Recalled historical memory {memory['memory_id']} at similarity {memory['similarity_score']:.2f}; "
            f"{memory['historical_resolution']}. Recommended {route.route_name}."
        )
