from app.graph.state import DispatchGraphState
from app.graph_memory.extractor import GraphMemoryContext
from app.graph_memory.protocols import GraphMemoryError
from app.graph_memory.service import GraphMemoryService


async def graph_memory_node(
    state: DispatchGraphState,
    graph_memory_service: GraphMemoryService | None,
) -> dict[str, object]:
    empty_patch: dict[str, object] = {
        "graph_memory_facts": [],
        "graph_memory_paths": [],
        "graph_memory_used": False,
        "graph_memory_error": None,
        "graph_memory_elapsed_ms": 0.0,
    }
    if graph_memory_service is None:
        return empty_patch

    context = GraphMemoryContext(
        driver_id=state["driver_id"],
        route_id=state["route_id"],
        anomaly_type=state["anomaly_type"],
        text=state.get("normalized_anomaly", state["anomaly_description"]),
        vehicle_id=state.get("vehicle_id"),
        weather=state.get("weather"),
    )
    try:
        recall = await graph_memory_service.recall(context)
    except GraphMemoryError:
        return {
            **empty_patch,
            "graph_memory_error": "Graph memory recall is temporarily unavailable.",
        }
    return {
        "graph_memory_facts": [fact.to_dict() for fact in recall.facts],
        "graph_memory_paths": [path.to_dict() for path in recall.paths],
        "graph_memory_used": bool(recall.facts or recall.paths),
        "graph_memory_error": None,
        "graph_memory_elapsed_ms": recall.elapsed_ms,
    }

