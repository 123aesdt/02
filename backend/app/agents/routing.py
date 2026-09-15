from decimal import Decimal

from app.graph.state import DispatchGraphState, RouteCandidateState
from app.real_routes.models import GeoPoint, RealRoadRoute
from app.real_routes.service import RealRoadRouteService
from app.recommendations.service import IssueRecommendationService
from app.road_network.models import PathResult
from app.road_network.service import RoadNetworkSnapshotService
from app.routing.models import RouteCandidate, RoutePlanningContext, RoutingResult
from app.routing.service import RoutingService


def _route_score_components_to_state(candidate: RouteCandidate) -> dict[str, str] | None:
    components = candidate.score_components
    if components is None:
        return None
    return {
        "normalized_minutes": format(components.normalized_minutes, "f"),
        "normalized_distance": format(components.normalized_distance, "f"),
        "normalized_risk": format(components.normalized_risk, "f"),
        "time_penalty": format(components.time_penalty, "f"),
        "distance_penalty": format(components.distance_penalty, "f"),
        "risk_penalty": format(components.risk_penalty, "f"),
    }


def _route_score_to_state(score: Decimal) -> str:
    two_decimal_score = score.quantize(Decimal("0.01"))
    return format(two_decimal_score if score == two_decimal_score else score, "f")


def route_candidate_to_state(candidate: RouteCandidate) -> RouteCandidateState:
    return {
        "route_id": candidate.route_id,
        "route_name": candidate.route_name,
        "distance_km": format(candidate.distance_km, "f"),
        "estimated_minutes": candidate.estimated_minutes,
        "risk_level": candidate.risk_level,
        "available": candidate.available,
        "reason": candidate.reason,
        "score": _route_score_to_state(candidate.score),
        "node_ids": list(candidate.node_ids),
        "edge_ids": list(candidate.edge_ids),
        "objective": candidate.objective,
        "algorithm_version": candidate.algorithm_version,
        "scoring_formula": candidate.scoring_formula,
        "score_components": _route_score_components_to_state(candidate),
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


def _geo_point_to_state(point: GeoPoint) -> dict[str, str | None]:
    return {
        "node_id": point.node_id,
        "longitude": format(point.longitude, "f"),
        "latitude": format(point.latitude, "f"),
    }


def _real_road_route_to_state(route: RealRoadRoute) -> dict[str, object]:
    return {
        "provider": route.provider,
        "source": route.source,
        "status": route.status,
        "coordinate_system": route.coordinate_system,
        "mapping_version": route.mapping_version,
        "distance_meters": route.distance_meters,
        "duration_seconds": route.duration_seconds,
        "waypoints": [_geo_point_to_state(point) for point in route.waypoints],
        "polyline": [_geo_point_to_state(point) for point in route.polyline],
        "fallback_reason": route.fallback_reason,
    }


def _planning_context(state: DispatchGraphState) -> RoutePlanningContext:
    original_vehicle_weight = state.get("original_vehicle_weight_tons") or state.get("vehicle_weight_tons")
    if original_vehicle_weight is None:
        raise ValueError("original_vehicle_weight_tons is required for offline road-network planning")
    active_vehicle_weight = state.get("active_vehicle_weight_tons") or state.get("selected_vehicle_gross_weight_tons") or original_vehicle_weight
    return RoutePlanningContext(
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
        original_vehicle_weight_tons=Decimal(str(original_vehicle_weight)),
        active_vehicle_weight_tons=Decimal(str(active_vehicle_weight)),
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
    road_network_snapshot_service: RoadNetworkSnapshotService | None = None,
    real_road_route_service: RealRoadRouteService | None = None,
) -> dict[str, object]:
    if routing_service is None:
        return {}
    if routing_service.can_plan and state.get("origin_node_id") and state.get("destination_node_id"):
        snapshot_state = state.get("road_network_snapshot")
        snapshot = road_network_snapshot_service.restore(snapshot_state) if road_network_snapshot_service is not None and snapshot_state is not None else None
        result = routing_service.plan(
            _planning_context(state),
            state["capacity_state"],
            state.get("affected_edge_ids", []),
            state.get("memory_results", []),
            road_network_snapshot=snapshot,
        )
        candidate_routes = [route_candidate_to_state(candidate) for candidate in result.candidate_routes]
        patch = {
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
        if result.recommended_path is not None and real_road_route_service is not None:
            patch["real_road_route"] = _real_road_route_to_state(
                await real_road_route_service.plan(result.recommended_path.node_ids)
            )
        return patch
    result = await routing_service.route(
        state["route_id"],
        state.get("memory_results", []),
        state.get("weather", "unknown"),
        state.get("road_condition", "unknown"),
        state.get("environment_risk", "elevated"),
        state["capacity_state"],
    )
    return _recommendation_patch(
        state,
        result,
        [route_candidate_to_state(candidate) for candidate in result.candidate_routes],
        recommendation_service,
    )
