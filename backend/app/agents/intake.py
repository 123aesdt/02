from datetime import UTC, datetime

from app.graph.state import DispatchGraphState


def intake_node(state: DispatchGraphState) -> dict[str, object]:
    description = state.get("anomaly_description", "")
    normalized = " ".join(description.split())
    if not all([state.get("task_id"), state.get("order_id"), state.get("anomaly_type"), normalized]):
        return {"requires_manual_review": True, "error_code": "INTAKE_VALIDATION_ERROR", "error_message": "Anomaly description is required."}
    patch: dict[str, object] = {"normalized_anomaly": normalized, "requires_manual_review": False}
    if not state.get("started_at"):
        patch["started_at"] = datetime.now(UTC).isoformat()
    return patch
