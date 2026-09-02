from app.graph.state import DispatchGraphState, RouteCandidateState
from app.recommendations.service import IssueRecommendationService
from app.routing.models import RouteCandidate
from app.routing.service import RoutingService


def route_candidate_to_state(candidate: RouteCandidate) -> RouteCandidateState:
    return {
        "route_id": candidate.route_id,
        "route_name": candidate.route_name,
        "distance_km": candidate.distance_km,
        "estimated_minutes": candidate.estimated_minutes,
        "risk_level": candidate.risk_level,
        "available": candidate.available,
        "reason": candidate.reason,
        "score": candidate.score,
    }


async def routing_node(
    state: DispatchGraphState,
    routing_service: RoutingService | None,
    recommendation_service: IssueRecommendationService | None = None,
) -> dict[str, object]:
    if routing_service is None:
        return {}
    result = await routing_service.route(
        state["route_id"],
        state.get("memory_results", []),
        state.get("weather", "unknown"),
        state.get("road_condition", "unknown"),
        state.get("environment_risk", "elevated"),
        state["capacity_state"],
    )
    candidate_routes = [route_candidate_to_state(candidate) for candidate in result.candidate_routes]
    recommendation = (recommendation_service or IssueRecommendationService()).recommend(
        anomaly_type=state["anomaly_type"],
        anomaly_description=state["anomaly_description"],
        vehicle_status=state.get("vehicle_status"),
        environment_risk=state.get("environment_risk"),
        capacity_status=state.get("capacity_state", {}).get("capacity_status"),
        candidate_routes=candidate_routes,
        recommended_route=result.recommended_route,
    )
    action_only = recommendation.issue_category in {
        "VEHICLE_BREAKDOWN",
        "CARGO",
        "CAPACITY",
        "OTHER",
    }
    route_rejected = result.decision == "REROUTE" and recommendation.recommended_route is None
    requires_manual_review = result.requires_manual_review or action_only or route_rejected
    return {
        "candidate_routes": candidate_routes,
        "recommended_route": recommendation.recommended_route,
        "identified_issue": recommendation.issue_category,
        "issue_subtype": recommendation.issue_subtype,
        "recommended_action": recommendation.recommended_action,
        "analysis_mode": recommendation.analysis_mode,
        "decision": "MANUAL_REVIEW" if requires_manual_review else result.decision,
        "decision_reason": f"{recommendation.analysis_reason} 路由依据：{result.decision_reason}",
        "memory_adopted": result.memory_adopted,
        "adopted_memory_id": result.adopted_memory_id,
        "requires_manual_review": requires_manual_review,
    }
