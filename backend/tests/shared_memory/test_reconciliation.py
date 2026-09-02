import pytest

from app.models.shared_memory import MemoryMutationAttempt
from app.shared_memory.reconciler import MemoryMutationReconciler
from tests.shared_memory.test_mutation_service import harness, seed_fact
from tests.shared_memory.test_partial_failure import hybrid_command


@pytest.mark.asyncio
async def test_memory_reconciliation(sqlite_factory) -> None:
    item = hybrid_command()
    seed_fact(sqlite_factory, item, content_fingerprint="a" * 64)
    service, repository, vector, graph, _ = harness(sqlite_factory)
    graph.fail_stage_code = "NEO4J_WRITE_FAILED"
    partial = await service.mutate(item)
    reconciler = MemoryMutationReconciler(service)

    result = await reconciler.resume_mutation(partial.mutation_id)

    assert result.status == "APPLIED"
    assert (vector.stage_calls, graph.stage_calls) == (1, 2)
    assert repository.load_fact(result.fact_key).version == 8
    with sqlite_factory() as session:
        assert session.query(MemoryMutationAttempt).count() == 2


@pytest.mark.asyncio
async def test_reverse_partial_reconciliation_has_no_duplicate_edge(sqlite_factory) -> None:
    item = hybrid_command()
    seed_fact(sqlite_factory, item, content_fingerprint="a" * 64)
    service, _, vector, graph, _ = harness(sqlite_factory)
    vector.fail_stage_code = "QDRANT_WRITE_FAILED"
    partial = await service.mutate(item)

    result = await MemoryMutationReconciler(service).resume_mutation(partial.mutation_id)

    assert result.status == "APPLIED"
    assert (vector.stage_calls, graph.stage_calls) == (2, 1)


@pytest.mark.asyncio
async def test_finalize_crash_is_reconciled(sqlite_factory) -> None:
    item = hybrid_command()
    seed_fact(sqlite_factory, item, content_fingerprint="a" * 64)
    service, repository, vector, graph, _ = harness(sqlite_factory)
    graph.fail_activate_code = "NEO4J_ACTIVATE_FAILED"
    partial = await service.mutate(item)

    assert partial.status == "PARTIAL"
    assert repository.load_fact(partial.fact_key).version == 8
    assert (partial.vector_status, partial.graph_status) == ("ACTIVE", "STAGED")

    result = await MemoryMutationReconciler(service).resume_mutation(partial.mutation_id)

    assert result.status == "APPLIED"
    assert (vector.stage_calls, graph.stage_calls) == (1, 1)
    assert (vector.activate_calls, graph.activate_calls) == (1, 2)

