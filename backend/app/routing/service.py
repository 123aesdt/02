from dataclasses import replace

from app.graph.state import CapacityState, MemoryRecallState
from app.routing.models import RouteCandidate, RoutingResult
from app.routing.provider import RouteProvider


class RoutingService:
    def __init__(self, route_provider: RouteProvider, *, memory_adoption_threshold: float) -> None:
        self._route_provider = route_provider
        self._memory_adoption_threshold = memory_adoption_threshold

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

    def _memory_route(self, memory: MemoryRecallState | None) -> str | None:
        if memory is None or memory["similarity_score"] < self._memory_adoption_threshold:
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
                score=-1000.0,
            )
        score = 100.0 - candidate.distance_km * 2 - candidate.estimated_minutes * 0.1
        if environment_risk in {"high", "critical"} and candidate.risk_level in {"medium", "high"}:
            score -= 15.0
        if candidate.route_id == memory_route:
            score += 30.0
        if capacity_status == "LIMITED":
            score -= 5.0
        return replace(candidate, score=score)

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
