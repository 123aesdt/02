import traceback
from datetime import UTC, datetime

import pytest
from qdrant_client import QdrantClient, models

from app.workspace_reads.qdrant_repository import (
    InvalidVectorMemoryCursor,
    QdrantVectorMemoryReadRepository,
    VectorMemoryReadUnavailable,
)


def write_two_memories(
    client: QdrantClient,
    *,
    dimension: int,
    provenances: tuple[str | None, str | None] = (None, None),
) -> None:
    client.create_collection(
        "entity_resolution_memory",
        vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
    )
    client.upsert(
        "entity_resolution_memory",
        points=[
            models.PointStruct(
                id=1,
                vector=[1.0] + [0.0] * (dimension - 1),
                payload={
                    "memory_id": "memory-rain-li",
                    "driver_id": "driver-li",
                    "route_id": "xinping-road",
                    "anomaly_type": "rain_slippery",
                    "resolution_text": "建议改走102国道",
                    "metadata": {"text": "李师傅 雨天 新平路"},
                    "created_at": "2026-08-29T08:00:00+00:00",
                    "projection_status": "ACTIVE",
                    **({"data_provenance": provenances[0]} if provenances[0] else {}),
                },
            ),
            models.PointStruct(
                id=2,
                vector=[0.0, 1.0] + [0.0] * (dimension - 2),
                payload={
                    "memory_id": "memory-engine",
                    "driver_id": "driver-wang",
                    "route_id": "county-road-8",
                    "anomaly_type": "engine_fault",
                    "resolution_text": "更换备用车辆继续配送",
                    "metadata": {"text": "发动机故障"},
                    "created_at": "2026-08-29T09:00:00+00:00",
                    **({"data_provenance": provenances[1]} if provenances[1] else {}),
                },
            ),
        ],
    )


@pytest.mark.asyncio
async def test_vector_memory_page_uses_actual_dimension_and_omits_vectors():
    client = QdrantClient(":memory:")
    write_two_memories(client, dimension=128)
    repository = QdrantVectorMemoryReadRepository(client, "entity_resolution_memory")

    page = await repository.list_records(limit=1, cursor=None)

    assert page.vector_dimension == 128
    assert page.items[0].memory_id == "memory-rain-li"
    assert page.items[0].historical_resolution == "建议改走102国道"
    assert page.items[0].created_at == datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    assert not hasattr(page.items[0], "vector")
    assert not hasattr(page.items[0], "metadata")
    assert page.next_cursor is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provenances", "expected"),
    [
        ((None, None), "LIVE"),
        (("DEMO", "DEMO"), "DEMO"),
        (("DEMO", None), "MIXED"),
    ],
)
async def test_vector_memory_provenance_uses_the_full_collection(provenances, expected):
    client = QdrantClient(":memory:")
    write_two_memories(client, dimension=32, provenances=provenances)

    page = await QdrantVectorMemoryReadRepository(client, "entity_resolution_memory").list_records(limit=1)

    assert page.total == 2
    assert page.provenance == expected


@pytest.mark.asyncio
async def test_vector_memory_page_extracts_dimension_from_a_named_vector_collection():
    client = QdrantClient(":memory:")
    client.create_collection(
        "named_memory",
        vectors_config={
            "semantic": models.VectorParams(size=64, distance=models.Distance.COSINE),
        },
    )
    client.upsert(
        "named_memory",
        points=[
            models.PointStruct(
                id=1,
                vector={"semantic": [1.0] + [0.0] * 63},
                payload={"memory_id": "named-memory-1"},
            )
        ],
    )
    repository = QdrantVectorMemoryReadRepository(client, "named_memory")

    page = await repository.list_records()

    assert page.vector_dimension == 64


@pytest.mark.asyncio
async def test_vector_memory_page_does_not_invent_one_dimension_for_mixed_named_vectors():
    client = QdrantClient(":memory:")
    client.create_collection(
        "mixed_named_memory",
        vectors_config={
            "semantic": models.VectorParams(size=64, distance=models.Distance.COSINE),
            "routing": models.VectorParams(size=32, distance=models.Distance.COSINE),
        },
    )
    repository = QdrantVectorMemoryReadRepository(client, "mixed_named_memory")

    page = await repository.list_records()

    assert page.vector_dimension is None


@pytest.mark.asyncio
async def test_vector_memory_page_uses_an_opaque_cursor_for_the_second_page():
    client = QdrantClient(":memory:")
    write_two_memories(client, dimension=128)
    repository = QdrantVectorMemoryReadRepository(client, "entity_resolution_memory")

    first_page = await repository.list_records(limit=1, cursor=None)
    second_page = await repository.list_records(limit=1, cursor=first_page.next_cursor)

    assert first_page.next_cursor != "1"
    assert [item.memory_id for item in second_page.items] == ["memory-engine"]
    assert second_page.items[0].projection_status is None
    assert second_page.next_cursor is None


@pytest.mark.asyncio
async def test_missing_vector_memory_collection_is_an_empty_live_page():
    repository = QdrantVectorMemoryReadRepository(QdrantClient(":memory:"), "entity_resolution_memory")

    page = await repository.list_records()

    assert page.items == ()
    assert page.total == 0
    assert page.next_cursor is None
    assert page.vector_dimension is None
    assert page.provenance == "LIVE"


@pytest.mark.asyncio
async def test_vector_memory_page_rejects_a_malformed_cursor_stably():
    repository = QdrantVectorMemoryReadRepository(QdrantClient(":memory:"), "entity_resolution_memory")

    with pytest.raises(InvalidVectorMemoryCursor, match="invalid vector memory cursor"):
        await repository.list_records(cursor="not-a-qdrant-cursor")


@pytest.mark.asyncio
async def test_vector_memory_page_normalizes_qdrant_transport_errors():
    class UnavailableClient:
        def collection_exists(self, _collection: str) -> bool:
            raise RuntimeError("POST http://qdrant.internal:6333/collections/secret?token=leaked")

    repository = QdrantVectorMemoryReadRepository(UnavailableClient(), "entity_resolution_memory")

    with pytest.raises(VectorMemoryReadUnavailable, match="vector memory read unavailable") as error:
        await repository.list_records()

    assert "qdrant.internal" not in str(error.value)
    assert "token" not in str(error.value)


@pytest.mark.asyncio
async def test_vector_memory_page_suppresses_transport_secrets_from_its_traceback():
    secret = "https://qdrant.internal:6333/?token=leaked Authorization: Bearer secret-value"

    class UnavailableClient:
        def collection_exists(self, _collection: str) -> bool:
            raise RuntimeError(secret)

    repository = QdrantVectorMemoryReadRepository(UnavailableClient(), "entity_resolution_memory")

    with pytest.raises(VectorMemoryReadUnavailable) as error:
        await repository.list_records()

    rendered_traceback = "".join(traceback.format_exception(error.value))
    assert secret not in str(error.value)
    assert secret not in rendered_traceback
    assert "Authorization" not in rendered_traceback
