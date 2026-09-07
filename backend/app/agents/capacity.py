from decimal import Decimal

from app.capacity.models import CapacityResult
from app.capacity.service import CapacityEvaluationError, CapacityService
from app.fleet.models import FleetAllocationRequest, VehicleCandidate
from app.fleet.service import FleetAllocationService
from app.graph.state import CapacityState, DispatchGraphState
from app.road_network.models import PathResult
from app.road_network.service import RoadNetworkSnapshotService


def capacity_result_to_state(result: CapacityResult) -> CapacityState:
    return {
        "driver_available": result.driver_available,
        "vehicle_available": result.vehicle_available,
        "load_ratio": result.load_ratio,
        "station_load_ratio": result.station_load_ratio,
        "capacity_status": result.capacity_status,
        "risk_level": result.risk_level,
        "reason": result.reason,
        "provider_name": result.provider_name,
    }


def _path_to_state(path: PathResult | None) -> dict[str, object] | None:
    if path is None:
        return None
    return {
        "objective": str(path.objective),
        "node_ids": list(path.node_ids),
        "edge_ids": list(path.edge_ids),
        "distance_km": str(path.distance_km),
        "estimated_minutes": path.estimated_minutes,
        "risk_cost": str(path.risk_cost),
        "visited_node_count": path.visited_node_count,
    }


def _score_components_to_state(candidate: VehicleCandidate) -> dict[str, str] | None:
    if candidate.score_components is None:
        return None
    return {
        "eta_penalty": format(candidate.score_components.eta_penalty, "f"),
        "distance_penalty": format(candidate.score_components.distance_penalty, "f"),
        "load_penalty": format(candidate.score_components.load_penalty, "f"),
        "road_risk_penalty": format(candidate.score_components.road_risk_penalty, "f"),
        "same_station_bonus": format(candidate.score_components.same_station_bonus, "f"),
        "cargo_exact_match_bonus": format(candidate.score_components.cargo_exact_match_bonus, "f"),
    }


def _candidate_to_state(candidate: VehicleCandidate) -> dict[str, object]:
    return {
        "vehicle_id": candidate.vehicle_id,
        "driver_id": candidate.driver_id,
        "vehicle_status": candidate.vehicle_status,
        "remaining_load_kg": str(candidate.remaining_load_kg),
        "gross_weight_tons": str(candidate.gross_weight_tons),
        "cargo_capability": candidate.cargo_capability,
        "pickup_route": _path_to_state(candidate.pickup_route),
        "pickup_distance_km": str(candidate.pickup_distance_km) if candidate.pickup_distance_km is not None else None,
        "pickup_eta_minutes": candidate.pickup_eta_minutes,
        "score": str(candidate.score) if candidate.score is not None else None,
        "score_components": _score_components_to_state(candidate),
        "scoring_formula": "FLEET_SCORE_V1",
        "eligible": candidate.eligible,
        "exclusion_reasons": list(candidate.exclusion_reasons),
    }


async def capacity_node(
    state: DispatchGraphState,
    capacity_service: CapacityService | None,
    fleet_allocation_service: FleetAllocationService | None = None,
    road_network_snapshot_service: RoadNetworkSnapshotService | None = None,
) -> dict[str, object]:
    if capacity_service is None:
        available = state.get("vehicle_status", "NORMAL") == "NORMAL"
        capacity_state: CapacityState = {
            "driver_available": available,
            "vehicle_available": available,
            "load_ratio": 0.0,
            "station_load_ratio": None,
            "capacity_status": "AVAILABLE" if available else "UNAVAILABLE",
            "risk_level": "low" if available else "high",
            "reason": None,
            "provider_name": "sandtable_graph",
        }
    else:
        try:
            result = await capacity_service.evaluate(
                state["driver_id"],
                state.get("vehicle_id"),
                state["route_id"],
                state["order_id"],
                vehicle_status=state.get("vehicle_status", "NORMAL"),
                cargo_weight_kg=Decimal(state["cargo_weight_kg"]) if state.get("cargo_weight_kg") is not None else None,
                cargo_type=state.get("cargo_type"),
            )
        except CapacityEvaluationError:
            return {
                "capacity_state": {
                    "driver_available": False,
                    "vehicle_available": False,
                    "load_ratio": 0.0,
                    "station_load_ratio": None,
                    "capacity_status": "UNKNOWN",
                    "risk_level": "high",
                    "reason": "Capacity evaluation is temporarily unavailable.",
                    "provider_name": "unknown",
                },
                "requires_manual_review": True,
                "error_code": "CAPACITY_EVALUATION_ERROR",
                "error_message": "Capacity evaluation is temporarily unavailable.",
            }
        capacity_state = capacity_result_to_state(result)

    if state.get("vehicle_status") in {"BROKEN", "UNAVAILABLE", "MAINTENANCE"} and fleet_allocation_service is not None:
        snapshot_state = state.get("road_network_snapshot")
        road_network_snapshot = (
            road_network_snapshot_service.restore(snapshot_state) if road_network_snapshot_service is not None and snapshot_state is not None else None
        )
        allocation = fleet_allocation_service.allocate(
            FleetAllocationRequest(
                original_vehicle_id=state.get("vehicle_id", ""),
                incident_node_id=state.get("incident_node_id") or state.get("origin_node_id", ""),
                cargo_weight_kg=Decimal(state.get("cargo_weight_kg", "0")),
                cargo_type=state.get("cargo_type", "GENERAL"),
                destination_node_id=state.get("destination_node_id"),
            ),
            road_network_snapshot=road_network_snapshot,
        )
        candidates = [_candidate_to_state(candidate) for candidate in allocation.candidates]
        if allocation.vehicle_reassigned:
            capacity_state.update(
                {
                    "driver_available": True,
                    "vehicle_available": True,
                    "capacity_status": "REASSIGNED",
                    "risk_level": "low",
                    "reason": None,
                }
            )
            selected_weight = next(candidate.gross_weight_tons for candidate in allocation.candidates if candidate.vehicle_id == allocation.selected_vehicle_id)
            return {
                "capacity_state": capacity_state,
                "candidate_vehicles": candidates,
                "selected_vehicle_id": allocation.selected_vehicle_id,
                "selected_driver_id": allocation.selected_driver_id,
                "selected_vehicle_gross_weight_tons": format(selected_weight, "f"),
                "active_vehicle_weight_tons": format(selected_weight, "f"),
                "vehicle_reassigned": True,
                "pickup_route": _path_to_state(allocation.pickup_route),
                "requires_manual_review": False,
            }
        capacity_state.update(
            {
                "vehicle_available": False,
                "capacity_status": "UNAVAILABLE",
                "risk_level": "high",
                "reason": allocation.reason,
            }
        )
        return {
            "capacity_state": capacity_state,
            "candidate_vehicles": candidates,
            "requires_manual_review": True,
            "error_code": "NO_REPLACEMENT_VEHICLE",
            "error_message": "No eligible replacement vehicle is available.",
        }
    return {"capacity_state": capacity_state}
