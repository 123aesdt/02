from datetime import UTC, datetime

from app.graph.state import DispatchGraphState
from app.road_network.service import RoadNetworkSnapshotService
from app.sandtable.service import RoadLocationUnresolved, SandtableContextService, VehicleAssignmentMismatch


def intake_node(
    state: DispatchGraphState,
    sandtable_context_service: SandtableContextService | None = None,
    road_network_snapshot_service: RoadNetworkSnapshotService | None = None,
) -> dict[str, object]:
    description = state.get("anomaly_description", "")
    normalized = " ".join(description.split())
    if not all([state.get("task_id"), state.get("order_id"), state.get("anomaly_type"), normalized]):
        return {"requires_manual_review": True, "error_code": "INTAKE_VALIDATION_ERROR", "error_message": "Anomaly description is required."}
    patch: dict[str, object] = {"normalized_anomaly": normalized, "requires_manual_review": False}
    if sandtable_context_service is not None:
        patch["sandtable_context_loaded"] = False
        try:
            context = sandtable_context_service.resolve(state["order_id"], state["anomaly_type"], normalized, state.get("vehicle_id"))
        except LookupError:
            if not state.get("started_at"):
                patch["started_at"] = datetime.now(UTC).isoformat()
            return patch
        except RoadLocationUnresolved:
            return {
                **patch,
                "sandtable_context_loaded": True,
                "requires_manual_review": True,
                "error_code": "ROAD_LOCATION_UNRESOLVED",
                "error_message": "The reported road location could not be resolved uniquely.",
            }
        except VehicleAssignmentMismatch as error:
            vehicle_weight = format(error.context.vehicle_weight_tons, "f")
            return {
                **patch,
                "sandtable_context_loaded": True,
                "vehicle_id": error.context.current_vehicle_id,
                "driver_id": error.context.current_driver_id or state["driver_id"],
                "vehicle_weight_tons": vehicle_weight,
                "original_vehicle_weight_tons": vehicle_weight,
                "active_vehicle_weight_tons": vehicle_weight,
                "requires_manual_review": True,
                "error_code": "VEHICLE_ASSIGNMENT_MISMATCH",
                "error_message": "请求车辆与订单当前分配车辆不一致，请人工核对订单车辆信息。",
            }
        vehicle_weight = format(context.vehicle_weight_tons, "f")
        snapshot_state = road_network_snapshot_service.capture() if road_network_snapshot_service is not None else None
        patch.update(
            {
                "sandtable_context_loaded": True,
                "cargo_weight_kg": format(context.cargo_weight_kg, "f"),
                "cargo_type": context.cargo_type,
                "origin_node_id": context.origin_node_id,
                "destination_node_id": context.destination_node_id,
                "vehicle_id": context.current_vehicle_id,
                "vehicle_weight_tons": vehicle_weight,
                "original_vehicle_weight_tons": vehicle_weight,
                "active_vehicle_weight_tons": vehicle_weight,
                "driver_id": context.current_driver_id or state["driver_id"],
                "incident_node_id": context.incident_node_id,
                "affected_edge_ids": list(context.affected_edge_ids),
                "blocked_edge_ids": list(context.affected_edge_ids),
                "road_network_version": snapshot_state["version"] if snapshot_state is not None else context.road_network_version,
            }
        )
        if snapshot_state is not None:
            patch["road_network_snapshot"] = snapshot_state
    if not state.get("started_at"):
        patch["started_at"] = datetime.now(UTC).isoformat()
    return patch
