import asyncio
import json

import pytest

from app.agents.graph_memory import graph_memory_node
from app.graph_memory.extractor import DeterministicGraphTripleExtractor
from app.graph_memory.fake_repository import FakeGraphMemoryRepository
from app.graph_memory.protocols import GraphMemoryError
from app.graph_memory.seed import seed_graph_memory
from app.graph_memory.service import GraphMemoryService


def _state() -> dict[str, object]:
    return {
        "task_id": "task-001",
        "order_id": 1,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-cold-a",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "李师傅驾驶冷链车A，在雨天经过新平路时报告道路湿滑。",
        "normalized_anomaly": "李师傅驾驶冷链车A，在雨天经过新平路时报告道路湿滑。",
        "memory_results": [{"memory_id": "memory-rain-li"}],
    }


@pytest.mark.asyncio
async def test_graph_memory_agent_emits_serializable_patch_without_replacing_vector_memory():
    repository = FakeGraphMemoryRepository()
    await seed_graph_memory(repository)
    service = GraphMemoryService(repository, DeterministicGraphTripleExtractor())
    state = _state()

    patch = await graph_memory_node(state, service)

    json.dumps(patch, ensure_ascii=False)
    assert patch["graph_memory_used"] is True
    assert patch["graph_memory_error"] is None
    assert any(fact["relation_type"] == "ALTERNATIVE_TO" for fact in patch["graph_memory_facts"])
    assert patch["graph_memory_paths"]
    assert state["memory_results"] == [{"memory_id": "memory-rain-li"}]
    assert "memory_results" not in patch


class _FailingRepository(FakeGraphMemoryRepository):
    async def upsert_entity(self, entity):
        raise GraphMemoryError("bolt://neo4j:7687 internal-secret")


@pytest.mark.asyncio
async def test_graph_memory_failure_degrades_safely_and_hides_internal_error():
    service = GraphMemoryService(_FailingRepository(), DeterministicGraphTripleExtractor())

    patch = await graph_memory_node(_state(), service)

    assert patch == {
        "graph_memory_facts": [],
        "graph_memory_paths": [],
        "graph_memory_used": False,
        "graph_memory_error": "Graph memory recall is temporarily unavailable.",
        "graph_memory_elapsed_ms": 0.0,
    }
    assert "internal-secret" not in json.dumps(patch)


@pytest.mark.asyncio
async def test_graph_memory_agent_does_not_swallow_cancellation():
    class CancellingService:
        async def recall(self, context):
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await graph_memory_node(_state(), CancellingService())

