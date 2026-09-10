from app.audit.models import AuditResult
from app.audit.service import AuditPersistenceError, AuditService
from app.graph.state import AuditResultState, DispatchGraphState


def audit_result_to_state(result: AuditResult) -> AuditResultState:
    return {
        "audit_status": result.audit_status,
        "passed": result.passed,
        "reason": result.reason,
        "checks": result.checks,
        "dispatch_id": result.dispatch_id,
        "requires_manual_review": result.requires_manual_review,
        "audit_record_id": result.audit_record_id,
    }


async def audit_node(
    state: DispatchGraphState,
    audit_service: AuditService | None,
) -> dict[str, object]:
    if audit_service is None:
        return {}
    evidence = {
        "task_id": state["task_id"],
        "route_id": state["route_id"],
        "anomaly_type": state.get("anomaly_type"),
        "vehicle_id": state.get("vehicle_id"),
        "selected_vehicle_id": state.get("selected_vehicle_id"),
        "selected_driver_id": state.get("selected_driver_id"),
        "candidate_vehicles": state.get("candidate_vehicles", []),
        "cargo_weight_kg": state.get("cargo_weight_kg"),
        "cargo_type": state.get("cargo_type"),
        "blocked_edge_ids": state.get("blocked_edge_ids", []),
        "original_path": state.get("original_path"),
        "recommended_path": state.get("recommended_path"),
        "pickup_route": state.get("pickup_route"),
        "road_network_edges": state.get("road_network_edges", []),
        "memory_results": state.get("memory_results", []),
        "memory_adopted": state.get("memory_adopted", False),
        "adopted_memory_id": state.get("adopted_memory_id"),
        "graph_memory_used": state.get("graph_memory_used", False),
        "graph_memory_error": state.get("graph_memory_error"),
        "graph_memory_facts": state.get("graph_memory_facts", []),
        "graph_memory_paths": state.get("graph_memory_paths", []),
        "fallback_used": state.get("fallback_used", False),
        "fallback_reason": state.get("fallback_reason"),
        "recommended_route": state.get("recommended_route"),
        "analysis_mode": state.get("analysis_mode"),
        "identified_issue": state.get("identified_issue"),
        "issue_subtype": state.get("issue_subtype"),
        "environment_risk": state.get("environment_risk"),
        "capacity_state": state.get("capacity_state", {}),
        "decision": state.get("decision"),
        "decision_reason": state.get("decision_reason"),
        "dispatch_result": state.get("dispatch_result", {}),
        "requires_manual_review": state.get("requires_manual_review", False),
        "error_code": state.get("error_code"),
    }
    try:
        result = audit_service.audit(evidence)
    except AuditPersistenceError:
        return {
            "requires_manual_review": True,
            "error_code": "AUDIT_PERSISTENCE_ERROR",
            "error_message": "Audit result could not be persisted.",
            "audit_result": None,
        }
    return {
        "audit_result": audit_result_to_state(result),
        "requires_manual_review": result.requires_manual_review,
    }
