from datetime import UTC, datetime

import pytest
from qdrant_client import QdrantClient

from app.agents.intake import intake_node
from app.agents.memory import entity_memory_node
from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.memory.models import MemoryRecord
from app.memory.qdrant_repository import QdrantMemoryRepository
from app.memory.service import EntityMemoryService
from app.providers.embedding.fake import FakeEmbeddingProvider
from app.providers.errors import ProviderTimeout


def _record(memory_id: str, text: str, resolution: str) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        driver_id="driver-li",
        route_id="xinping-road",
        anomaly_type="rain_slippery",
        resolution_text=resolution,
        metadata={"text": text},
        created_at=datetime.now(UTC),
    )


async def _memory_service() -> EntityMemoryService:
    repository = QdrantMemoryRepository(QdrantClient(":memory:"), "graph_memory", 128)
    service = EntityMemoryService(FakeEmbeddingProvider(128), repository)
    await service.remember(_record("memory-rain-li", "李师傅 雨天 新平路 道路湿滑", "建议改走102国道"))
    await service.remember(_record("memory-engine", "车辆 发动机 故障", "更换备用车辆继续配送"))
    await service.remember(_record("memory-overload", "配送站 货物 积压 容量不足", "分流邻近配送站"))
    await service.remember(_record("memory-road-closed", "道路 完全 封闭 无法 通行", "绕行备用县道"))
    return service


def _state() -> dict[str, object]:
    return {
        "task_id": "task-001",
        "order_id": 1,
        "driver_id": "driver-li",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "李师傅在雨天经过新平路，当前道路出现湿滑风险，需要选择更安全的路线。",
    }


@pytest.mark.asyncio
async def test_memory_agent_recall():
    state = _state()
    state.update(intake_node(state))

    patch = await entity_memory_node(state, await _memory_service())

    assert patch["memory_results"][0]["memory_id"] == "memory-rain-li"
    assert patch["memory_results"][0]["historical_resolution"] == "建议改走102国道"
    assert patch["memory_results"][0]["similarity_score"] > 0


@pytest.mark.asyncio
async def test_memory_agent_writes_state_patch_without_mutating_input():
    state = _state()
    state.update(intake_node(state))

    patch = await entity_memory_node(state, await _memory_service())

    assert "memory_results" not in state
    assert set(patch) == {"memory_results"}
    assert isinstance(patch["memory_results"], list)


@pytest.mark.asyncio
async def test_memory_agent_handles_empty_recall():
    service = EntityMemoryService(FakeEmbeddingProvider(128), QdrantMemoryRepository(QdrantClient(":memory:"), "empty_graph_memory", 128))
    state = _state()
    state.update(intake_node(state))

    patch = await entity_memory_node(state, service)

    assert patch == {"memory_results": []}


class _TimeoutEmbeddingProvider:
    vector_dimension = 128

    async def embed_text(self, text: str) -> list[float]:
        raise ProviderTimeout("upstream timed out")


@pytest.mark.asyncio
async def test_memory_agent_failure_behavior():
    service = EntityMemoryService(
        _TimeoutEmbeddingProvider(),
        QdrantMemoryRepository(QdrantClient(":memory:"), "failed_graph_memory", 128),
    )
    state = _state()
    state.update(intake_node(state))

    patch = await entity_memory_node(state, service)

    assert patch["memory_results"] == []
    assert patch["error_code"] == "MEMORY_RECALL_ERROR"
    assert patch["error_message"] == "Entity memory recall is temporarily unavailable."


@pytest.mark.asyncio
async def test_graph_intake_to_memory_flow():
    graph = build_graph(GraphDependencies(entity_memory_service=await _memory_service()))

    result = await graph.ainvoke(_state())

    assert result["normalized_anomaly"] == "李师傅在雨天经过新平路，当前道路出现湿滑风险，需要选择更安全的路线。"
    assert result["memory_results"][0]["memory_id"] == "memory-rain-li"
