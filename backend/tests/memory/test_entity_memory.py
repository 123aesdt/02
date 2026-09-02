from datetime import UTC, datetime

import pytest
from qdrant_client import QdrantClient

from app.memory.models import MemoryRecord
from app.memory.qdrant_repository import EmbeddingDimensionError, QdrantMemoryRepository
from app.memory.service import EntityMemoryService
from app.providers.embedding.fake import FakeEmbeddingProvider


def record(memory_id, text, resolution):
    return MemoryRecord(memory_id, "driver-li", "xinping-road", "rain_slippery", resolution, {"text": text}, datetime.now(UTC))


@pytest.mark.asyncio
async def test_memory_recall_uses_qdrant_vector_search_without_filters():
    repo = QdrantMemoryRepository(QdrantClient(":memory:"), "entity_resolution_memory", 128)
    service = EntityMemoryService(FakeEmbeddingProvider(128), repo)
    await service.remember(record("memory-rain-li", "李师傅 雨天 新平路 道路湿滑", "建议改走102国道"))
    await service.remember(record("memory-engine", "车辆 发动机 故障", "更换备用车辆继续配送"))
    await service.remember(record("memory-overload", "配送站 货物 积压 容量不足", "分流邻近配送站"))
    await service.remember(record("memory-road-closed", "道路 完全 封闭 无法 通行", "绕行备用县道"))
    recalls = await service.recall("李师傅在雨天经过新平路，道路湿滑风险", top_k=2)
    assert recalls[0].memory_id == "memory-rain-li"
    assert recalls[0].historical_resolution == "建议改走102国道"
    assert recalls[0].similarity_score > recalls[1].similarity_score


@pytest.mark.asyncio
async def test_repeated_business_memory_upsert_updates_the_same_qdrant_point():
    repo = QdrantMemoryRepository(QdrantClient(":memory:"), "updates", 128)
    service = EntityMemoryService(FakeEmbeddingProvider(128), repo)
    original = record("memory-rain-li", "李师傅 雨天 新平路 道路湿滑", "旧路线")
    await service.remember(original)
    await service.remember(record("memory-rain-li", "李师傅 雨天 新平路 道路湿滑", "建议改走102国道"))
    recalls = await service.recall("李师傅 雨天 新平路 道路湿滑", top_k=2)
    assert len(recalls) == 1
    assert recalls[0].memory_id == "memory-rain-li"
    assert recalls[0].historical_resolution == "建议改走102国道"


@pytest.mark.asyncio
async def test_memory_empty_and_dimension_validation():
    repo = QdrantMemoryRepository(QdrantClient(":memory:"), "empty", 8)
    service = EntityMemoryService(FakeEmbeddingProvider(8), repo)
    assert await service.recall("nothing", top_k=2) == []
    with pytest.raises(EmbeddingDimensionError):
        await repo.upsert(record("wrong", "x", "y"), [0.0] * 7)
