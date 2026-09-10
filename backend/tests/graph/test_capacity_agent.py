import asyncio
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient, MockTransport, Response
from qdrant_client import QdrantClient

from app.agents.capacity import capacity_node
from app.capacity.models import CapacitySnapshot
from app.capacity.provider import CapacityProviderError, InMemoryCapacityProvider
from app.capacity.service import CapacityService
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


class _BrokenCapacityProvider:
    async def get_capacity(self, driver_id: str, vehicle_id: str | None, route_id: str, order_id: int) -> CapacitySnapshot:
        raise CapacityProviderError("capacity source unavailable")


def _state() -> dict[str, object]:
    return {
        "task_id": "task-001",
        "order_id": 1,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-001",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
    }


def _capacity_service() -> CapacityService:
    return CapacityService(
        InMemoryCapacityProvider({("driver-li", "vehicle-001"): CapacitySnapshot(True, True, 0.45, 0.60, "in_memory_capacity")}),
        limited_threshold=0.8,
        unavailable_threshold=1.0,
    )


async def _memory_service() -> EntityMemoryService:
    repository = QdrantMemoryRepository(QdrantClient(":memory:"), "capacity_graph_memory", 128)
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


def _environment_service() -> EnvironmentService:
    return EnvironmentService(_SuccessfulEnvironmentProvider(), StaticRouteFallbackProvider(), CircuitBreaker(3, 5.0))


@pytest.mark.asyncio
async def test_capacity_agent_writes_state():
    patch = await capacity_node(_state(), _capacity_service())

    assert patch == {
        "capacity_state": {
            "driver_available": True,
            "vehicle_available": True,
            "load_ratio": 0.45,
            "station_load_ratio": 0.60,
            "capacity_status": "AVAILABLE",
            "risk_level": "low",
            "reason": None,
            "provider_name": "in_memory_capacity",
        }
    }


@pytest.mark.asyncio
async def test_capacity_agent_handles_provider_failure():
    service = CapacityService(_BrokenCapacityProvider(), limited_threshold=0.8, unavailable_threshold=1.0)

    patch = await capacity_node(_state(), service)

    assert patch["capacity_state"]["capacity_status"] == "UNKNOWN"
    assert patch["requires_manual_review"] is True
    assert patch["error_code"] == "CAPACITY_EVALUATION_ERROR"


@pytest.mark.asyncio
async def test_capacity_agent_reads_canonical_vehicle_status():
    state = _state()
    state["vehicle_status"] = "BROKEN"

    patch = await capacity_node(state, _capacity_service())

    assert patch["capacity_state"]["vehicle_available"] is False
    assert patch["capacity_state"]["capacity_status"] == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_capacity_agent_preserves_legacy_flow_without_sandtable_context():
    state = _state()
    state["sandtable_context_loaded"] = False
    service = CapacityService(InMemoryCapacityProvider({}), limited_threshold=0.8, unavailable_threshold=1.0)

    patch = await capacity_node(state, service)

    assert patch["capacity_state"] == {
        "driver_available": True,
        "vehicle_available": True,
        "load_ratio": 0.0,
        "station_load_ratio": None,
        "capacity_status": "AVAILABLE",
        "risk_level": "low",
        "reason": None,
        "provider_name": "legacy_compatibility",
    }

@pytest.mark.asyncio
async def test_graph_intake_memory_environment_capacity_flow():
    graph = build_graph(
        GraphDependencies(
            entity_memory_service=await _memory_service(),
            environment_service=_environment_service(),
            capacity_service=_capacity_service(),
        )
    )

    result = await graph.ainvoke(_state())

    assert result["normalized_anomaly"] == "李师傅在雨天经过新平路，道路出现湿滑风险。"
    assert result["memory_results"][0]["memory_id"] == "memory-rain-li"
    assert result["memory_results"][0]["historical_resolution"] == "建议改走102国道"
    assert result["weather"] == "rain"
    assert result["road_condition"] == "wet"
    assert result["environment_risk"] == "high"
    assert result["capacity_state"]["capacity_status"] == "AVAILABLE"


@pytest.mark.asyncio
async def test_graph_environment_fallback_continues_to_capacity():
    async def handler(request):
        await asyncio.sleep(2.0)
        return Response(200, json={})

    async with AsyncClient(transport=MockTransport(handler)) as client:
        environment_service = EnvironmentService(
            HttpEnvironmentProvider("https://environment.test", client=client, timeout_seconds=0.8),
            StaticRouteFallbackProvider(),
            CircuitBreaker(3, 5.0),
        )
        graph = build_graph(
            GraphDependencies(
                entity_memory_service=await _memory_service(),
                environment_service=environment_service,
                capacity_service=_capacity_service(),
            )
        )
        result = await graph.ainvoke(_state())

    assert result["fallback_used"] is True
    assert result["capacity_state"]["capacity_status"] == "AVAILABLE"
