from datetime import UTC, datetime

from app.graph.state import DispatchGraphState
from app.sandtable.service import RoadLocationUnresolved, SandtableContextService, VehicleAssignmentMismatch


def intake_node(state: DispatchGraphState, sandtable_context_service: SandtableContextService | None = None) -> dict[str, object]:
    description = state.get("anomaly_description", "")
    normalized = " ".join(description.split())
    if not all([state.get("task_id"), state.get("order_id"), state.get("anomaly_type"), normalized]):
        return {"requires_manual_review": True, "error_code": "INTAKE_VALIDATION_ERROR", "error_message": "Anomaly description is required."}
    patch: dict[str, object] = {"normalized_anomaly": normalized, "requires_manual_review": False}
    if sandtable_context_service is not None:
        try:
            context = sandtable_context_service.resolve(
                state["order_id"], state["anomaly_type"], normalized, state.get("vehicle_id")
            )
        except RoadLocationUnresolved:
            return {
                **patch,
                "requires_manual_review": True,
                "error_code": "ROAD_LOCATION_UNRESOLVED",
                "error_message": "The reported road location could not be resolved uniquely.",
            }
        except VehicleAssignmentMismatch as error:
            return {
                **patch,
                "vehicle_id": error.context.current_vehicle_id,
                "driver_id": error.context.current_driver_id or state["driver_id"],
                "vehicle_weight_tons": format(error.context.vehicle_weight_tons, "f"),
                "requires_manual_review": True,
                "error_code": "VEHICLE_ASSIGNMENT_MISMATCH",
                "error_message": "请求车辆与订单当前分配车辆不一致，请人工核对订单车辆信息。",
            }
        patch.update(
            {
                "cargo_weight_kg": str(context.cargo_weight_kg),
                "cargo_type": context.cargo_type,
                "origin_node_id": context.origin_node_id,
                "destination_node_id": context.destination_node_id,
                "vehicle_id": context.current_vehicle_id,
                "vehicle_weight_tons": format(context.vehicle_weight_tons, "f"),
                "driver_id": context.current_driver_id or state["driver_id"],
                "incident_node_id": context.incident_node_id,
                "affected_edge_ids": list(context.affected_edge_ids),
                "blocked_edge_ids": list(context.affected_edge_ids),
                "road_network_version": context.road_network_version,
            }
        )
    if not state.get("started_at"):
        patch["started_at"] = datetime.now(UTC).isoformat()
    return patch
