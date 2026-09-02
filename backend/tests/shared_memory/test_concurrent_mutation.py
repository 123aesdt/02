import asyncio

import pytest

from app.shared_memory.service import MemoryMutationBusy
from tests.shared_memory.test_mutation_service import command, harness


class HoldingLock:
    def __init__(self) -> None:
        self.held = False
        self.entered = asyncio.Event()
        self.release_gate = asyncio.Event()

    async def acquire(self, fact_key):
        from app.shared_memory.redis_lock import MemoryLockHandle

        if self.held:
            return MemoryLockHandle(f"countyflow:lock:memory:{fact_key}", "other", False)
        self.held = True
        self.entered.set()
        return MemoryLockHandle(f"countyflow:lock:memory:{fact_key}", "owner", True)

    async def release(self, handle):
        await self.release_gate.wait()
        self.held = False
        return True


@pytest.mark.asyncio
async def test_memory_concurrent_mutation_race(sqlite_factory) -> None:
    lock = HoldingLock()
    service, repository, _, graph, _ = harness(sqlite_factory, lock=lock)
    item = command(idempotency_key="race-winner")
    first_task = asyncio.create_task(service.mutate(item))
    await lock.entered.wait()

    with pytest.raises(MemoryMutationBusy):
        await service.mutate(command(idempotency_key="race-loser"))

    lock.release_gate.set()
    first = await first_task
    assert repository.load_fact(first.fact_key).version == 1
    assert graph.stage_calls == 1

