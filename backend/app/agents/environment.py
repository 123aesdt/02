from app.graph.state import DispatchGraphState
from app.services.environment import EnvironmentService


async def environment_node(
    state: DispatchGraphState,
    environment_service: EnvironmentService | None,
) -> dict[str, object]:
    if environment_service is None:
        return {}
    result = await environment_service.get_environment(state["route_id"])
    return {
        "weather": result.weather,
        "road_condition": result.road_condition,
        "environment_risk": result.risk_level,
        "fallback_used": result.fallback_used,
        "fallback_reason": result.fallback_reason,
        "environment_provider": result.provider_name,
        "environment_elapsed_ms": result.elapsed_ms,
    }
