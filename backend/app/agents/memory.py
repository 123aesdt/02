from app.graph.state import DispatchGraphState, MemoryRecallState
from app.memory.models import MemoryRecall
from app.memory.service import EntityMemoryService, memory_recall_query
from app.providers.errors import ProviderError


def memory_recall_to_state(recall: MemoryRecall) -> MemoryRecallState:
    return {
        "memory_id": recall.memory_id,
        "similarity_score": recall.similarity_score,
        "driver_id": recall.driver_id,
        "route_id": recall.route_id,
        "anomaly_type": recall.anomaly_type,
        "historical_resolution": recall.historical_resolution,
        "metadata": dict(recall.metadata),
    }


async def entity_memory_node(
    state: DispatchGraphState,
    entity_memory_service: EntityMemoryService | None,
) -> dict[str, object]:
    if entity_memory_service is None:
        return {"memory_results": []}

    query = memory_recall_query(
        state["driver_id"],
        state["route_id"],
        state["anomaly_type"],
        state.get("normalized_anomaly", state["anomaly_description"]),
    )
    try:
        recalls = await entity_memory_service.recall(query)
    except ProviderError:
        return {
            "memory_results": [],
            "error_code": "MEMORY_RECALL_ERROR",
            "error_message": "Entity memory recall is temporarily unavailable.",
        }
    return {"memory_results": [memory_recall_to_state(recall) for recall in recalls]}
