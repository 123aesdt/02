from app.capacity.models import CapacityResult
from app.capacity.service import CapacityEvaluationError, CapacityService
from app.graph.state import CapacityState, DispatchGraphState


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


async def capacity_node(state: DispatchGraphState, capacity_service: CapacityService | None) -> dict[str, object]:
    if capacity_service is None:
        return {}
    try:
        result = await capacity_service.evaluate(
            state["driver_id"],
            state.get("vehicle_id"),
            state["route_id"],
            state["order_id"],
            vehicle_status=state.get("vehicle_status", "NORMAL"),
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
    return {"capacity_state": capacity_result_to_state(result)}
