import pytest

from app.shared_memory.sqlalchemy_repository import MemoryIdempotencyConflict
from tests.shared_memory.test_mutation_service import command, harness


@pytest.mark.asyncio
async def test_memory_idempotent_replay(sqlite_factory) -> None:
    item = command(idempotency_key="stable-idempotency-key")
    service, _, vector, graph, events = harness(sqlite_factory)

    first = await service.mutate(item)
    second = await service.mutate(item)

    assert second == first
    assert (vector.stage_calls, graph.stage_calls, len(events.events)) == (0, 1, 2)


@pytest.mark.asyncio
async def test_memory_idempotency_payload_conflict(sqlite_factory) -> None:
    service, _, _, graph, _ = harness(sqlite_factory)
    await service.mutate(command(idempotency_key="reused-key"))

    with pytest.raises(MemoryIdempotencyConflict):
        await service.mutate(
            command(idempotency_key="reused-key", value_json={"status": "Broken"})
        )
    assert graph.stage_calls == 1

