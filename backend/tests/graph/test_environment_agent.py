import asyncio
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient, MockTransport, Response
from qdrant_client import QdrantClient

from app.agents.environment import environment_node
from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.memory.models import MemoryRecord
from app.memory.qdrant_repository import QdrantMemoryRepository
from app.memory.service import EntityMemoryService
from app.providers.embedding.fake import FakeEmbeddingProvider
from app.providers.environment import EnvironmentResult, HttpEnvironmentProvider, StaticRouteFallbackProvider
from app.services.circuit_breaker import CircuitBreaker
from app.services.environment import EnvironmentService


class _SuccessfulEnvironmentProvider:
    async def get_environment(self, route_id: str) -> EnvironmentResult:
        return EnvironmentResult("rain", "wet", "high", "test_environment", False, None, 1.0)


def _state() -> dict[str, object]:
    return {
        "task_id": "task-001",
        "order_id": 1,
        "driver_id": "driver-li",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
    }


async def _memory_service() -> EntityMemoryService:
    repository = QdrantMemoryRepository(QdrantClient(":memory:"), "environment_graph_memory", 128)
    service = EntityMemoryService(FakeEmbeddingProvider(128), repository)
    await service.remember(
        MemoryRecord(
            "memory-rain-li",
            "driver-li",
            "xinping-road",
            "rain_slippery",
            "建议改走102国道",
            {"text": "李师傅 雨天 新平路 道路湿滑"},
            datetime.now(UTC),
        )
    )
    await service.remember(
        MemoryRecord(
            "memory-engine",
            "driver-wang",
            "county-road",
            "engine_failure",
            "更换备用车辆继续配送",
            {"text": "车辆 发动机 故障"},
            datetime.now(UTC),
        )
    )
    return service


def _successful_environment_service() -> EnvironmentService:
    return EnvironmentService(_SuccessfulEnvironmentProvider(), StaticRouteFallbackProvider(), CircuitBreaker(3, 5.0))


@pytest.mark.asyncio
async def test_environment_agent_writes_state():
    patch = await environment_node(_state(), _successful_environment_service())

    assert patch == {
        "weather": "rain",
        "road_condition": "wet",
        "environment_risk": "high",
        "fallback_used": False,
        "fallback_reason": None,
        "environment_provider": "test_environment",
        "environment_elapsed_ms": 1.0,
    }


@pytest.mark.asyncio
async def test_environment_agent_fallback_state():
    async def handler(request):
        await asyncio.sleep(2.0)
        return Response(200, json={})

    async with AsyncClient(transport=MockTransport(handler)) as client:
        service = EnvironmentService(
            HttpEnvironmentProvider("https://environment.test", client=client, timeout_seconds=0.8),
            StaticRouteFallbackProvider(),
            CircuitBreaker(3, 5.0),
        )
        patch = await environment_node(_state(), service)

    assert patch["fallback_used"] is True
    assert patch["fallback_reason"] == "Primary environment provider timed out."
    assert patch["weather"] == "unknown"
    assert patch["road_condition"] == "unknown"
    assert patch["environment_risk"] == "elevated"


@pytest.mark.asyncio
async def test_graph_intake_memory_environment_flow():
    graph = build_graph(
        GraphDependencies(
            entity_memory_service=await _memory_service(),
            environment_service=_successful_environment_service(),
        )
    )

    result = await graph.ainvoke(_state())

    assert result["normalized_anomaly"] == "李师傅在雨天经过新平路，道路出现湿滑风险。"
    assert result["memory_results"][0]["memory_id"] == "memory-rain-li"
    assert result["weather"] == "rain"
    assert result["road_condition"] == "wet"
    assert result["environment_risk"] == "high"


@pytest.mark.asyncio
async def test_graph_environment_fallback_flow():
    async def handler(request):
        await asyncio.sleep(2.0)
        return Response(200, json={})

    async with AsyncClient(transport=MockTransport(handler)) as client:
        service = EnvironmentService(
            HttpEnvironmentProvider("https://environment.test", client=client, timeout_seconds=0.8),
            StaticRouteFallbackProvider(),
            CircuitBreaker(3, 5.0),
        )
        graph = build_graph(GraphDependencies(entity_memory_service=await _memory_service(), environment_service=service))
        result = await graph.ainvoke(_state())

    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "Primary environment provider timed out."
    assert result["environment_risk"] == "elevated"
