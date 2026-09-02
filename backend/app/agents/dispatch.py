from app.core.errors import OptimisticLockConflict
from app.dispatch.models import DispatchResult
from app.dispatch.service import DispatchService
from app.graph.state import DispatchGraphState, DispatchResultState


def dispatch_result_to_state(result: DispatchResult) -> DispatchResultState:
    return {
        "dispatch_id": result.dispatch_id,
        "dispatch_no": result.dispatch_no,
        "status": result.status,
        "target_route_id": result.target_route_id,
        "version": result.version,
        "executed": result.executed,
    }


async def dispatch_node(state: DispatchGraphState, dispatch_service: DispatchService | None) -> dict[str, object]:
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
        )
    except OptimisticLockConflict:
        return {"requires_manual_review": True, "error_code": "DISPATCH_VERSION_CONFLICT", "error_message": "Dispatch was modified by another operation."}
    return {"dispatch_result": dispatch_result_to_state(result), "requires_manual_review": result.requires_manual_review}
