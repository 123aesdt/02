import pytest

from app.models.shared_memory import MemoryEvidence, MemoryMutation, MemoryMutationAttempt
from tests.shared_memory.test_mutation_service import command, harness


async def _applied(sqlite_factory):
    service, _, _, _, _ = harness(sqlite_factory)
    return await service.mutate(command(operator_id="auditor-7", source_id="inspection-42"))


@pytest.mark.asyncio
async def test_memory_audit(sqlite_factory) -> None:
    result = await _applied(sqlite_factory)

    with sqlite_factory() as session:
        mutation = session.query(MemoryMutation).one()
        evidence = session.query(MemoryEvidence).one()
        attempt = session.query(MemoryMutationAttempt).one()

    assert mutation.mutation_id == result.mutation_id
    assert (mutation.operator_id, mutation.source_id, mutation.fact_key) == (
        "auditor-7",
        "inspection-42",
        result.fact_key,
    )
    assert (mutation.before_version, mutation.after_version, mutation.decision) == (None, 1, "CREATE")
    assert (mutation.vector_status, mutation.graph_status, mutation.status) == (
        "NOT_REQUIRED",
        "ACTIVE",
        "APPLIED",
    )
    assert evidence.fact_id is not None
    assert (attempt.attempt_no, attempt.result, attempt.graph_after) == (1, "APPLIED", "ACTIVE")
