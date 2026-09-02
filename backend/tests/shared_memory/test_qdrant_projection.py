import asyncio
import time
from datetime import UTC, datetime

import pytest
from qdrant_client import QdrantClient

from app.memory.qdrant_repository import QdrantMemoryRepository
from app.shared_memory.protocols import VectorProjection
from app.shared_memory.qdrant_projection import QdrantMemoryProjection


def projection(version: int, resolution: str) -> VectorProjection:
    return VectorProjection(
        mutation_id=f"00000000-0000-0000-0000-00000000000{version}",
        fact_key="smf_" + "a" * 64,
        control_version=version,
        memory_id="vehicle-status-memory",
        vector=(1.0, 0.0, 0.0, 0.0),
        driver_id="driver-li",
        route_id="xinping-road",
        anomaly_type="vehicle_status",
        resolution_text=resolution,
        metadata={"text": resolution},
        expires_at=None,
    )


@pytest.fixture
def stores():
    client = QdrantClient(":memory:")
    projection_store = QdrantMemoryProjection(client, "shared-memory", 4)
    recall_store = QdrantMemoryRepository(client, "shared-memory", 4)
    return projection_store, recall_store


@pytest.mark.asyncio
async def test_memory_qdrant_retry_no_duplicate(stores) -> None:
    projection_store, _ = stores

    await projection_store.stage(projection(8, "Broken"))
    await projection_store.stage(projection(8, "Broken"))

    assert await projection_store.count_points("vehicle-status-memory", version=8) == 1


@pytest.mark.asyncio
async def test_qdrant_staged_projection_not_recalled(stores) -> None:
    projection_store, recall_store = stores
    v7 = projection(7, "Normal")
    v8 = projection(8, "Broken")
    await projection_store.stage(v7)
    await projection_store.activate(v7)
    await projection_store.retire_previous(v7)
    await projection_store.stage(v8)

    recalls = await recall_store.search([1.0, 0.0, 0.0, 0.0], top_k=5)

    assert [(item.historical_resolution, item.memory_id) for item in recalls] == [
        ("Normal", "vehicle-status-memory")
    ]


@pytest.mark.asyncio
async def test_qdrant_activation_retires_previous_version(stores) -> None:
    projection_store, recall_store = stores
    v7 = projection(7, "Normal")
    v8 = projection(8, "Broken")
    await projection_store.stage(v7)
    await projection_store.activate(v7)
    await projection_store.retire_previous(v7)
    await projection_store.stage(v8)
    await projection_store.activate(v8)
    await projection_store.retire_previous(v8)

    recalls = await recall_store.search([1.0, 0.0, 0.0, 0.0], top_k=5)

    assert [item.historical_resolution for item in recalls] == ["Broken"]
    assert await projection_store.probe(v7.mutation_id, 7) == "RETIRED"
    assert await projection_store.probe(v8.mutation_id, 8) == "ACTIVE"


@pytest.mark.asyncio
async def test_qdrant_expired_active_projection_not_recalled(stores) -> None:
    projection_store, recall_store = stores
    expired = projection(8, "Expired")
    expired = VectorProjection(**{**expired.__dict__, "expires_at": datetime(2026, 8, 26, tzinfo=UTC)})
    await projection_store.stage(expired)
    await projection_store.activate(expired)

    assert await recall_store.search([1.0, 0.0, 0.0, 0.0], top_k=5) == []


@pytest.mark.asyncio
async def test_qdrant_projection_does_not_block_asyncio_timeout() -> None:
    class SlowClient:
        def collection_exists(self, _collection: str) -> bool:
            time.sleep(0.2)
            return True

    projection_store = QdrantMemoryProjection(SlowClient(), "shared-memory", 4)

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.05):
            await projection_store.stage(projection(1, "Broken"))
