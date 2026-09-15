import asyncio

from app.vehicle_operations.protocols import Clock


class VehicleOperationsProgressor:
    def __init__(self, repository, clock: Clock, *, poll_interval_seconds: float = 1.0) -> None:
        self._repository = repository
        self._clock = clock
        self._poll_interval_seconds = poll_interval_seconds
        self._stop = asyncio.Event()

    async def run_once(self) -> None:
        now = self._clock.now()
        self._repository.advance_one_due_rescue(now)
        self._repository.advance_one_due_maintenance(now)

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll_interval_seconds)
            except TimeoutError:
                continue

    async def shutdown(self) -> None:
        self._stop.set()
