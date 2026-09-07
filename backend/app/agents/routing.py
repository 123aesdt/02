from decimal import Decimal

from app.graph.state import DispatchGraphState, RouteCandidateState
from app.recommendations.service import IssueRecommendationService
from app.road_network.models import PathResult
from app.routing.models import RouteCandidate, RoutingResult
from app.routing.service import RoutingService
from app.sandtable.models import SandtableTaskContext


def route_candidate_to_state(candidate: RouteCandidate) -> RouteCandidateState:
    return {
        "route_id": candidate.route_id,
        "route_name": candidate.route_name,
        "distance_km": format(candidate.distance_km, "f"),
        "estimated_minutes": candidate.estimated_minutes,
        "risk_level": candidate.risk_level,
        "available": candidate.available,
        "reason": candidate.reason,
        "score": format(candidate.score, "f"),
        "node_ids": list(candidate.node_ids),
        "edge_ids": list(candidate.edge_ids),
        "objective": candidate.objective,
        "algorithm_version": candidate.algorithm_version,
        "scoring_formula": candidate.scoring_formula,
        "road_network_version": candidate.road_network_version,
        "visited_node_count": candidate.visited_node_count,
        "risk_cost": str(candidate.risk_cost) if candidate.risk_cost is not None else None,
    }


def _path_to_state(path: PathResult | None) -> dict[str, object] | None:
    if path is None:
        return None
    return {
        "objective": path.objective.value,
        "node_ids": list(path.node_ids),
        "edge_ids": list(path.edge_ids),
        "distance_km": str(path.distance_km),
        "estimated_minutes": path.estimated_minutes,
        "risk_cost": str(path.risk_cost),
        "visited_node_count": path.visited_node_count,
    }


def _sandtable_context(state: DispatchGraphState) -> SandtableTaskContext:
    vehicle_weight = state.get("selected_vehicle_gross_weight_tons") or state.get("vehicle_weight_tons")
    if vehicle_weight is None:
        raise ValueError("vehicle_weight_tons is required for offline road-network planning")
    return SandtableTaskContext(
        order_id=state["order_id"],
        order_no=str(state["order_id"]),
        cargo_weight_kg=Decimal(state.get("cargo_weight_kg", "0")),
        cargo_type=state.get("cargo_type", "GENERAL"),
        origin_node_id=state["origin_node_id"],
        destination_node_id=state["destination_node_id"],
        current_vehicle_id=state.get("selected_vehicle_id") or state.get("vehicle_id", ""),
        current_driver_id=state.get("selected_driver_id") or state.get("driver_id"),
        incident_node_id=state.get("incident_node_id"),
        affected_edge_ids=tuple(state.get("affected_edge_ids", [])),
        road_network_version=state.get("road_network_version", 0),
        vehicle_weight_tons=Decimal(str(vehicle_weight)),
    )


def _recommendation_patch(
    state: DispatchGraphState,
    result: RoutingResult,
    candidate_routes: list[RouteCandidateState],
    recommendation_service: IssueRecommendationService | None,
) -> dict[str, object]:
    recommendation = (recommendation_service or IssueRecommendationService()).recommend(
        anomaly_type=state["anomaly_type"],
        anomaly_description=state["anomaly_description"],
        vehicle_status=state.get("vehicle_status"),
        environment_risk=state.get("environment_risk"),
        capacity_status=state.get("capacity_state", {}).get("capacity_status"),
        candidate_routes=candidate_routes,
        recommended_route=result.recommended_route,
    )
    reassigned_breakdown = recommendation.issue_category == "VEHICLE_BREAKDOWN" and state.get("capacity_state", {}).get("capacity_status") == "REASSIGNED"
    recommended_route = result.recommended_route if reassigned_breakdown else recommendation.recommended_route
    action_only = recommendation.issue_category in {"VEHICLE_BREAKDOWN", "CARGO", "CAPACITY", "OTHER"} and not reassigned_breakdown
    route_rejected = result.decision == "REROUTE" and recommended_route is None
    requires_manual_review = result.requires_manual_review or action_only or route_rejected
    return {
        "candidate_routes": candidate_routes,
        "recommended_route": recommended_route,
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


async def routing_node(
    state: DispatchGraphState,
    routing_service: RoutingService | None,
    recommendation_service: IssueRecommendationService | None = None,
) -> dict[str, object]:
    if routing_service is None:
        return {}
    if routing_service.can_plan and state.get("origin_node_id") and state.get("destination_node_id"):
        result = routing_service.plan(_sandtable_context(state), state["capacity_state"], state.get("affected_edge_ids", []), state.get("memory_results", []))
        candidate_routes = [route_candidate_to_state(candidate) for candidate in result.candidate_routes]
        return {
            **_recommendation_patch(state, result, candidate_routes, recommendation_service),
            **(
                {
                    "error_code": "NO_REACHABLE_ROUTE",
                    "error_message": "排除受影响道路后不存在可达配送路线，请人工复核。",
                }
                if result.routing_status == "NO_REACHABLE_ROUTE"
                else {}
            ),
            "blocked_edge_ids": list(result.blocked_edge_ids),
            "original_path": _path_to_state(result.original_path),
            "recommended_path": (
                {**_path_to_state(result.recommended_path), "scoring_formula": "ROUTE_SCORE_V1"} if result.recommended_path is not None else None
            ),
            "routing_algorithm": "DIJKSTRA_V1",
            "routing_status": result.routing_status,
            "road_network_version": result.road_network_version,
            "distance_delta_km": (
                str(result.recommended_path.distance_km - result.original_path.distance_km)
                if result.recommended_path is not None and result.original_path is not None
                else None
            ),
            "eta_delta_minutes": (
                result.recommended_path.estimated_minutes - result.original_path.estimated_minutes
                if result.recommended_path is not None and result.original_path is not None
                else None
            ),
            "road_network_nodes": result.road_network_nodes,
            "road_network_edges": result.road_network_edges,
        }
    result = await routing_service.route(
        state["route_id"],
        state.get("memory_results", []),
        state.get("weather", "unknown"),
        state.get("road_condition", "unknown"),
        state.get("environment_risk", "elevated"),
        state["capacity_state"],
    )
    return _recommendation_patch(state, result, [route_candidate_to_state(candidate) for candidate in result.candidate_routes], recommendation_service)
