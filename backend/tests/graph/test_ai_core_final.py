import asyncio
import json

import pytest
from httpx import AsyncClient, MockTransport, Response
from qdrant_client import QdrantClient
from sqlalchemy import select

from app.audit.service import AuditPersistenceError, AuditService
from app.capacity.models import CapacitySnapshot
from app.capacity.provider import InMemoryCapacityProvider
from app.capacity.service import CapacityService
from app.core.errors import OptimisticLockConflict
from app.dispatch.service import DispatchService
from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.graph_memory.extractor import DeterministicGraphTripleExtractor
from app.graph_memory.fake_repository import FakeGraphMemoryRepository
from app.graph_memory.seed import seed_graph_memory
from app.graph_memory.service import GraphMemoryService
from app.memory.qdrant_repository import QdrantMemoryRepository
from app.memory.service import EntityMemoryService
from app.models.audit import AuditRecord
from app.models.dispatch import Dispatch
from app.providers.environment import (
    EnvironmentResult,
    HttpEnvironmentProvider,
    StaticRouteFallbackProvider,
)
from app.providers.errors import ProviderTimeout
from app.services.circuit_breaker import CircuitBreaker
from app.services.environment import EnvironmentService
from tests.graph.test_routing_agent import _memory_service, _routing_service
from tests.unit.test_dispatch_service import _service


class _RainEnvironmentProvider:
    async def get_environment(self, route_id: str) -> EnvironmentResult:
        return EnvironmentResult("heavy_rain", "slippery", "high", "test_environment", False, None, 1.0)


class _FailingEnvironmentProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def get_environment(self, route_id: str) -> EnvironmentResult:
        self.calls += 1
        raise ProviderTimeout("environment timed out")


class _TimeoutEmbeddingProvider:
    vector_dimension = 128

    async def embed_text(self, text: str) -> list[float]:
        raise ProviderTimeout("memory provider timed out")


def _state() -> dict[str, object]:
    return {
        "task_id": "task-001",
        "order_id": 1,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-001",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险，需要选择更安全的路线。",
    }


def _available_capacity_service() -> CapacityService:
    return CapacityService(
        InMemoryCapacityProvider({("driver-li", "vehicle-001"): CapacitySnapshot(True, True, 0.45, 0.60, "in_memory_capacity")}),
        limited_threshold=0.8,
        unavailable_threshold=1.0,
    )


def _unavailable_capacity_service() -> CapacityService:
    return CapacityService(
        InMemoryCapacityProvider({("driver-li", "vehicle-001"): CapacitySnapshot(False, True, 0.45, 0.60, "in_memory_capacity")}),
        limited_threshold=0.8,
        unavailable_threshold=1.0,
    )


async def _graph(
    factory,
    environment_service: EnvironmentService,
    *,
    capacity_service: CapacityService | None = None,
    memory_service: EntityMemoryService | None = None,
    dispatch_service: object | None = None,
    audit_service: object | None = None,
    graph_memory_service: GraphMemoryService | None = None,
):
    return build_graph(
        GraphDependencies(
            entity_memory_service=memory_service or await _memory_service(),
            graph_memory_service=graph_memory_service,
            environment_service=environment_service,
            capacity_service=capacity_service or _available_capacity_service(),
            routing_service=_routing_service(),
            dispatch_service=dispatch_service or DispatchService(factory),
            audit_service=audit_service or AuditService(factory),
        )
    )


@pytest.mark.asyncio
async def test_ai_core_happy_path_has_json_state_and_durable_facts():
    temp, engine, factory = _service()
    try:
        graph = await _graph(
            factory,
            EnvironmentService(_RainEnvironmentProvider(), StaticRouteFallbackProvider(), CircuitBreaker(3, 5.0)),
        )
        result = await graph.ainvoke(_state())
        json.dumps(result)
        with factory() as session:
            dispatch = session.scalar(select(Dispatch).where(Dispatch.id == result["dispatch_result"]["dispatch_id"]))
            audit = session.scalar(select(AuditRecord).where(AuditRecord.id == result["audit_result"]["audit_record_id"]))

        assert result["normalized_anomaly"] == "李师傅在雨天经过新平路，道路出现湿滑风险，需要选择更安全的路线。"
        assert result["memory_results"][0]["memory_id"] == "memory-rain-li"
        assert result["memory_results"][0]["historical_resolution"] == "建议改走102国道"
        assert result["environment_risk"] == "high"
        assert result["capacity_state"]["capacity_status"] == "AVAILABLE"
        assert result["recommended_route"] == "national-102"
        assert (result["memory_adopted"], result["adopted_memory_id"], result["decision"]) == (True, "memory-rain-li", "REROUTE")
        assert result["dispatch_result"]["executed"] is True
        assert result["dispatch_result"]["target_route_id"] == "national-102"
        assert result["audit_result"]["audit_status"] == "APPROVED"
        assert result["audit_result"]["passed"] is True
        assert result["requires_manual_review"] is False
        assert (dispatch.original_route_id, dispatch.target_route_id, dispatch.fallback_used) == ("xinping-road", "national-102", False)
        assert dispatch.decision_reason
        assert dispatch.version == 1
        assert (audit.task_id, audit.dispatch_id, audit.result) == (1, dispatch.id, "APPROVED")
        assert audit.reason
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_v2_a_dual_memory_core_preserves_v1_decision_and_adds_graph_evidence():
    repository = FakeGraphMemoryRepository()
    await seed_graph_memory(repository)
    graph_memory_service = GraphMemoryService(repository, DeterministicGraphTripleExtractor())
    temp, engine, factory = _service()
    try:
        graph = await _graph(
            factory,
            EnvironmentService(_RainEnvironmentProvider(), StaticRouteFallbackProvider(), CircuitBreaker(3, 5.0)),
            graph_memory_service=graph_memory_service,
        )

        result = await graph.ainvoke(_state())

        facts = {
            (fact["source"]["entity_id"], fact["relation_type"], fact["target"]["entity_id"])
            for fact in result["graph_memory_facts"]
        }
        assert result["memory_results"][0]["memory_id"] == "memory-rain-li"
        assert ("driver-li", "HAS_RISK_ON", "xinping-road") in facts
        assert ("xinping-road", "HIGH_RISK_WHEN", "rain") in facts
        assert ("national-102", "ALTERNATIVE_TO", "xinping-road") in facts
        assert (result["recommended_route"], result["decision"]) == ("national-102", "REROUTE")
        assert result["dispatch_result"]["executed"] is True
        assert result["audit_result"]["audit_status"] == "APPROVED"
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_ai_core_environment_timeout_fallback_reaches_approved_audit():
    async def handler(request):
        await asyncio.sleep(2.0)
        return Response(200, json={})

    temp, engine, factory = _service()
    try:
        async with AsyncClient(transport=MockTransport(handler)) as client:
            environment_service = EnvironmentService(
                HttpEnvironmentProvider("https://environment.test", client=client, timeout_seconds=0.8),
                StaticRouteFallbackProvider(),
                CircuitBreaker(3, 5.0),
            )
            result = await (await _graph(factory, environment_service)).ainvoke(_state())
        with factory() as session:
            dispatch = session.scalar(select(Dispatch).where(Dispatch.id == result["dispatch_result"]["dispatch_id"]))

        assert 600 <= result["environment_elapsed_ms"] < 1000
        assert result["fallback_used"] is True
        assert result["fallback_reason"] == "Primary environment provider timed out."
        assert result["recommended_route"] == "national-102"
        assert result["dispatch_result"]["executed"] is True
        assert result["audit_result"]["audit_status"] == "APPROVED"
        assert (dispatch.fallback_used, dispatch.fallback_reason) == (True, result["fallback_reason"])
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_ai_core_open_circuit_uses_quick_fallback_and_completes():
    primary = _FailingEnvironmentProvider()
    environment_service = EnvironmentService(primary, StaticRouteFallbackProvider(), CircuitBreaker(1, 5.0))
    await environment_service.get_environment("xinping-road")
    temp, engine, factory = _service()
    try:
        result = await (await _graph(factory, environment_service)).ainvoke(_state())

        assert primary.calls == 1
        assert result["environment_elapsed_ms"] < 100
        assert result["fallback_reason"] == "Environment circuit breaker is open."
        assert result["dispatch_result"]["executed"] is True
        assert result["audit_result"]["audit_status"] == "APPROVED"
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_ai_core_unavailable_capacity_persists_manual_review_draft():
    temp, engine, factory = _service()
    try:
        graph = await _graph(
            factory,
            EnvironmentService(_RainEnvironmentProvider(), StaticRouteFallbackProvider(), CircuitBreaker(3, 5.0)),
            capacity_service=_unavailable_capacity_service(),
        )
        result = await graph.ainvoke(_state())
        with factory() as session:
            dispatches = list(session.scalars(select(Dispatch)))

        assert result["capacity_state"]["capacity_status"] == "UNAVAILABLE"
        assert result["decision"] == "MANUAL_REVIEW"
        assert result["dispatch_result"]["executed"] is False
        assert result["audit_result"]["audit_status"] == "REVIEW_REQUIRED"
        assert result["requires_manual_review"] is True
        assert len(dispatches) == 1
        assert dispatches[0].id == result["dispatch_result"]["dispatch_id"]
        assert dispatches[0].status == "REVIEW_REQUIRED"
        assert dispatches[0].target_route_id is None
        assert dispatches[0].recommended_action
        assert dispatches[0].analysis_mode == "EIGHT_AGENT_RULE_ASSISTED"
        assert result["audit_result"]["audit_record_id"] is not None
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_ai_core_memory_failure_is_safe_and_graph_continues():
    temp, engine, factory = _service()
    try:
        memory_service = EntityMemoryService(
            _TimeoutEmbeddingProvider(),
            QdrantMemoryRepository(QdrantClient(":memory:"), "final_memory_failure", 128),
        )
        result = await (
            await _graph(
                factory,
                EnvironmentService(_RainEnvironmentProvider(), StaticRouteFallbackProvider(), CircuitBreaker(3, 5.0)),
                memory_service=memory_service,
            )
        ).ainvoke(_state())

        assert result["memory_results"] == []
        assert result["error_code"] == "MEMORY_RECALL_ERROR"
        assert result["error_message"] == "Entity memory recall is temporarily unavailable."
        assert result["dispatch_result"]["executed"] is True
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_ai_core_dispatch_conflict_and_audit_failure_are_safe():
    class ConflictDispatchService:
        def execute(self, *args: object) -> object:
            raise OptimisticLockConflict(1)

    class FailingAuditService:
        def audit(self, evidence: object) -> object:
            raise AuditPersistenceError("internal database failure")

    temp, engine, factory = _service()
    try:
        conflict_result = await (
            await _graph(
                factory,
                EnvironmentService(_RainEnvironmentProvider(), StaticRouteFallbackProvider(), CircuitBreaker(3, 5.0)),
                dispatch_service=ConflictDispatchService(),
            )
        ).ainvoke(_state())
        audit_failure_result = await (
            await _graph(
                factory,
                EnvironmentService(_RainEnvironmentProvider(), StaticRouteFallbackProvider(), CircuitBreaker(3, 5.0)),
                audit_service=FailingAuditService(),
            )
        ).ainvoke(_state())

        assert conflict_result["error_code"] == "DISPATCH_VERSION_CONFLICT"
        assert conflict_result["audit_result"]["audit_status"] == "REVIEW_REQUIRED"
        assert conflict_result["requires_manual_review"] is True
        assert audit_failure_result["audit_result"] is None
        assert audit_failure_result["error_code"] == "AUDIT_PERSISTENCE_ERROR"
        assert audit_failure_result["error_message"] == "Audit result could not be persisted."
        assert "internal database failure" not in audit_failure_result["error_message"]
    finally:
        engine.dispose()
        temp.cleanup()
