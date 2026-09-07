from app.core.errors import OptimisticLockConflict
from app.dispatch.models import DispatchResult
from app.dispatch.service import DispatchService, VehicleReservationConflict
from app.graph.state import DispatchGraphState, DispatchResultState


def dispatch_result_to_state(result: DispatchResult) -> DispatchResultState:
    return {
        "dispatch_id": result.dispatch_id,
        "dispatch_no": result.dispatch_no,
        "status": result.status,
        "target_route_id": result.target_route_id,
        "original_vehicle_id": result.original_vehicle_id,
        "target_vehicle_id": result.target_vehicle_id,
        "target_driver_id": result.target_driver_id,
        "version": result.version,
        "executed": result.executed,
    }


async def dispatch_node(
    state: DispatchGraphState,
    dispatch_service: DispatchService | None,
) -> dict[str, object]:
    if dispatch_service is None:
        return {}
    try:
        result = dispatch_service.execute(
            state["task_id"],
            state["order_id"],
            state["route_id"],
            state.get("recommended_route"),
            state.get("decision", "MANUAL_REVIEW"),
            state.get("decision_reason", "Manual review required."),
            state.get("fallback_used", False),
            state.get("fallback_reason"),
            state.get("requires_manual_review", False),
            state.get("recommended_action"),
            state.get("analysis_mode"),
            state.get("issue_subtype"),
            state.get("vehicle_id"),
            state.get("candidate_vehicles", []),
            state.get("incident_node_id"),
            {
                "algorithm_version": "FLEET_SCORE_V1",
                "candidates": state.get("candidate_vehicles", []),
                "pickup_route": state.get("pickup_route"),
            },
            {
                "algorithm_version": state.get("routing_algorithm", "DIJKSTRA_V1"),
                "road_network_version": state.get("road_network_version"),
                "blocked_edge_ids": state.get("blocked_edge_ids", []),
                "recommended_path": state.get("recommended_path"),
                "candidate_routes": state.get("candidate_routes", []),
            },
        )
    except VehicleReservationConflict:
        return {
            "requires_manual_review": True,
            "error_code": "VEHICLE_RESERVATION_CONFLICT",
            "error_message": "Replacement vehicle reservation conflicted with another dispatch.",
        }
    except OptimisticLockConflict:
        return {
            "requires_manual_review": True,
            "error_code": "DISPATCH_VERSION_CONFLICT",
            "error_message": "Dispatch was modified by another operation.",
        }
    patch: dict[str, object] = {
        "dispatch_result": dispatch_result_to_state(result),
        "requires_manual_review": result.requires_manual_review,
    }
    if result.target_vehicle_id is not None:
        patch["selected_vehicle_id"] = result.target_vehicle_id
    if result.target_driver_id is not None:
        patch["selected_driver_id"] = result.target_driver_id
    return patch