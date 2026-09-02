import asyncio
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient, MockTransport, Response
from qdrant_client import QdrantClient

from app.agents.routing import routing_node
from app.capacity.models import CapacitySnapshot
from app.capacity.provider import InMemoryCapacityProvider
from app.capacity.service import CapacityService
from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.memory.models import MemoryRecord
from app.memory.qdrant_repository import QdrantMemoryRepository
from app.memory.service import EntityMemoryService
from app.providers.embedding.fake import FakeEmbeddingProvider
from app.providers.environment import EnvironmentResult, HttpEnvironmentProvider, StaticRouteFallbackProvider
from app.recommendations.service import IssueRecommendationService
from app.routing.provider import InMemoryRouteProvider
from app.routing.service import RoutingService
from app.services.circuit_breaker import CircuitBreaker
from app.services.environment import EnvironmentService


class _RainEnvironmentProvider:
    async def get_environment(self, route_id: str) -> EnvironmentResult:
        return EnvironmentResult("heavy_rain", "slippery", "high", "test_environment", False, None, 1.0)


def _state() -> dict[str, object]:
    return {
        "task_id": "task-001",
        "order_id": 1,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-001",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
        "weather": "heavy_rain",
        "road_condition": "slippery",
        "environment_risk": "high",
        "capacity_state": {
            "driver_available": True,
            "vehicle_available": True,
            "load_ratio": 0.45,
            "station_load_ratio": 0.60,
            "capacity_status": "AVAILABLE",
            "risk_level": "low",
            "reason": None,
            "provider_name": "in_memory_capacity",
        },
        "memory_results": [
            {
                "memory_id": "memory-rain-li",
                "similarity_score": 0.9,
                "driver_id": "driver-li",
                "route_id": "xinping-road",
                "anomaly_type": "rain_slippery",
                "historical_resolution": "建议改走102国道",
                "metadata": {},
            }
        ],
    }


def _routing_service() -> RoutingService:
    return RoutingService(InMemoryRouteProvider.default_catalog(), memory_adoption_threshold=0.75)


async def _memory_service() -> EntityMemoryService:
    service = EntityMemoryService(FakeEmbeddingProvider(128), QdrantMemoryRepository(QdrantClient(":memory:"), "routing_graph_memory", 128))
    await service.remember(
        MemoryRecord(
            "memory-rain-li", "driver-li", "xinping-road", "rain_slippery", "建议改走102国道", {"text": "李师傅 雨天 新平路 道路湿滑"}, datetime.now(UTC)
        )
    )
    await service.remember(
        MemoryRecord("memory-engine", "driver-wang", "county-road", "engine_failure", "更换备用车辆继续配送", {"text": "车辆 发动机 故障"}, datetime.now(UTC))
    )
    return service


def _environment_service() -> EnvironmentService:
    return EnvironmentService(_RainEnvironmentProvider(), StaticRouteFallbackProvider(), CircuitBreaker(3, 5.0))


def _capacity_service() -> CapacityService:
    return CapacityService(
        InMemoryCapacityProvider({("driver-li", "vehicle-001"): CapacitySnapshot(True, True, 0.45, 0.60, "in_memory_capacity")}),
        limited_threshold=0.8,
        unavailable_threshold=1.0,
    )


@pytest.mark.asyncio
async def test_routing_agent_writes_state():
    patch = await routing_node(_state(), _routing_service())

    assert patch["recommended_route"] == "national-102"
    assert patch["memory_adopted"] is True
    assert patch["adopted_memory_id"] == "memory-rain-li"


@pytest.mark.asyncio
async def test_routing_agent_turns_a_tire_report_into_an_action_without_a_route():
    state = _state()
    state.update(
        {
            "anomaly_type": "VEHICLE_BREAKDOWN",
            "anomaly_description": "右后轮爆胎，车辆无法继续行驶",
            "vehicle_status": "BROKEN",
        }
    )

    patch = await routing_node(state, _routing_service(), IssueRecommendationService())

    assert patch["identified_issue"] == "VEHICLE_BREAKDOWN"
    assert patch["issue_subtype"] == "TIRE"
    assert "更换轮胎" in patch["recommended_action"]
    assert patch["recommended_route"] is None
    assert patch["analysis_mode"] == "EIGHT_AGENT_RULE_ASSISTED"
    assert "右后轮爆胎" in patch["decision_reason"]


@pytest.mark.asyncio
async def test_graph_intake_memory_environment_capacity_routing_flow():
    graph = build_graph(
        GraphDependencies(
            entity_memory_service=await _memory_service(),
            environment_service=_environment_service(),
            capacity_service=_capacity_service(),
            routing_service=_routing_service(),
        )
    )

    result = await graph.ainvoke(
        {key: value for key, value in _state().items() if key not in {"weather", "road_condition", "environment_risk", "capacity_state", "memory_results"}}
    )

    assert result["memory_results"][0]["memory_id"] == "memory-rain-li"
    assert result["recommended_route"] == "national-102"
    assert result["memory_adopted"] is True
    assert "memory-rain-li" in result["decision_reason"]


@pytest.mark.asyncio
async def test_graph_environment_fallback_continues_to_routing():
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
                routing_service=_routing_service(),
            )
        )
        result = await graph.ainvoke(
            {
                "task_id": "task-002",
                "order_id": 2,
                "driver_id": "driver-li",
                "vehicle_id": "vehicle-001",
                "route_id": "xinping-road",
                "anomaly_type": "rain_slippery",
                "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
            }
        )

    assert result["fallback_used"] is True
    assert result["capacity_state"]["capacity_status"] == "AVAILABLE"
    assert result["recommended_route"] == "national-102"


