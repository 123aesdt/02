import asyncio
from datetime import UTC, datetime

import pytest

from app.vehicle_operations.progressor import VehicleOperationsProgressor


class FixedClock:
    def now(self):
        return datetime(2026, 9, 10, 10, 0, tzinfo=UTC)


class RecordingRepository:
    def __init__(self):
        self.rescue_calls = []
        self.maintenance_calls = []

    def advance_one_due_rescue(self, now):
        self.rescue_calls.append(now)
        return None

    def advance_one_due_maintenance(self, now):
        self.maintenance_calls.append(now)
        return None


@pytest.mark.asyncio
async def test_progressor_advances_at_most_one_record_per_domain_per_tick():
    repository = RecordingRepository()
    progressor = VehicleOperationsProgressor(repository, FixedClock(), poll_interval_seconds=0.01)

    await progressor.run_once()

    assert len(repository.rescue_calls) == 1
    assert len(repository.maintenance_calls) == 1
    assert repository.rescue_calls[0] == repository.maintenance_calls[0]


@pytest.mark.asyncio
async def test_progressor_shutdown_is_cancellation_safe():
    repository = RecordingRepository()
    progressor = VehicleOperationsProgressor(repository, FixedClock(), poll_interval_seconds=0.01)
    task = asyncio.create_task(progressor.run_forever())
    await asyncio.sleep(0.02)

    await progressor.shutdown()
    await asyncio.wait_for(task, timeout=0.2)

    assert repository.rescue_calls
