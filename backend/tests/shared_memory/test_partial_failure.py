import asyncio
from decimal import Decimal

import pytest

from app.shared_memory.identity import build_fact_key
from app.shared_memory.models import MemoryFactKind, MemoryTarget
from tests.shared_memory.test_mutation_service import command, harness, seed_fact


def hybrid_command(**changes):
    values = {
        "fact_kind": MemoryFactKind.HYBRID,
        "object_type": "Route",
        "object_id": "xinping-road",
        "predicate": "STATUS",
        "value_json": {"resolution": "Broken"},
        "expected_version": 7,
        "confidence": Decimal("0.9000"),
        "human_confirmed": True,
        "targets": frozenset({MemoryTarget.VECTOR, MemoryTarget.GRAPH}),
        "vector_memory_id": "vehicle-status-memory",
    }
    values.update(changes)
    return command(**values)


@pytest.mark.asyncio
async def test_memory_partial_qdrant_success(sqlite_factory) -> None:
    item = hybrid_command()
    seed_fact(sqlite_factory, item, content_fingerprint="a" * 64)
    service, repository, vector, graph, _ = harness(sqlite_factory)
    graph.fail_stage_code = "NEO4J_WRITE_FAILED"

    result = await service.mutate(item)

    assert (result.status, result.vector_status, result.graph_status) == (
        "PARTIAL",
        "STAGED",
        "FAILED",
    )
    assert repository.load_fact(result.fact_key).version == 7
    assert (vector.stage_calls, graph.stage_calls) == (1, 1)


@pytest.mark.asyncio
async def test_memory_partial_neo4j_success(sqlite_factory) -> None:
    item = hybrid_command()
    seed_fact(sqlite_factory, item, content_fingerprint="a" * 64)
    service, repository, vector, graph, _ = harness(sqlite_factory)
    vector.fail_stage_code = "QDRANT_WRITE_FAILED"

    result = await service.mutate(item)

    assert (result.status, result.vector_status, result.graph_status) == (
        "PARTIAL",
        "FAILED",
        "STAGED",
    )
    assert repository.load_fact(result.fact_key).version == 7
    assert (vector.stage_calls, graph.stage_calls) == (1, 1)


@pytest.mark.asyncio
async def test_partial_mutation_keeps_old_projection_active(sqlite_factory) -> None:
    item = hybrid_command()
    seed_fact(sqlite_factory, item, content_fingerprint="a" * 64)
    service, _, vector, graph, _ = harness(sqlite_factory)
    fact_key = build_fact_key(item)
    vector.active_versions[fact_key] = {7}
    graph.active_versions[fact_key] = {7}
    graph.fail_stage_code = "NEO4J_WRITE_FAILED"

    result = await service.mutate(item)

    assert result.status == "PARTIAL"
    assert vector.active_versions[fact_key] == {7}
    assert graph.active_versions[fact_key] == {7}
    assert vector.states[(result.mutation_id, 8)] == "STAGED"


@pytest.mark.asyncio
async def test_applied_requires_all_projections_active(sqlite_factory) -> None:
    item = hybrid_command()
    seed_fact(sqlite_factory, item, content_fingerprint="a" * 64)
    service, _, vector, graph, _ = harness(sqlite_factory)
    graph.fail_stage_code = "NEO4J_WRITE_FAILED"

    result = await service.mutate(item)

    assert result.status != "APPLIED"
    assert result.projection_incomplete is True
    assert vector.states[(result.mutation_id, 8)] == "STAGED"


@pytest.mark.asyncio
async def test_hung_projection_is_audited_as_partial_before_total_timeout(sqlite_factory) -> None:
    class HungProjection:
        async def stage(self, _projection) -> None:
            await asyncio.Event().wait()

    item = hybrid_command()
    seed_fact(sqlite_factory, item, content_fingerprint="a" * 64)
    service, _, _, _, _ = harness(sqlite_factory)
    service._graph_projection = HungProjection()
    service._timeout_seconds = 0.2
    service._projection_timeout_seconds = 0.05

    result = await service.mutate(item)

    assert result.status == "PARTIAL"
    assert result.graph_status == "FAILED"
    assert result.error_code == "PROJECTION_TIMEOUT"
