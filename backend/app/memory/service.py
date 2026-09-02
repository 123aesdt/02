from app.memory.models import MemoryRecord
from app.memory.qdrant_repository import QdrantMemoryRepository
from app.providers.embedding.base import EmbeddingProvider


def memory_context_text(driver_id: str, route_id: str, anomaly_type: str, detail: str) -> str:
    return f"司机 {driver_id} 路线 {route_id} 异常 {anomaly_type} {detail}"


def memory_to_embedding_text(record: MemoryRecord) -> str:
    return memory_context_text(
        record.driver_id,
        record.route_id,
        record.anomaly_type,
        f"解决方案 {record.resolution_text} {record.metadata.get('text', '')}",
    )


def memory_recall_query(driver_id: str, route_id: str, anomaly_type: str, normalized_anomaly: str) -> str:
    return memory_context_text(driver_id, route_id, anomaly_type, f"异常描述 {normalized_anomaly}")


class EntityMemoryService:
    def __init__(self, embedding_provider: EmbeddingProvider, repository: QdrantMemoryRepository) -> None:
        self._embedding, self._repository = embedding_provider, repository

    async def remember(self, record: MemoryRecord) -> None:
        await self._repository.upsert(record, await self._embedding.embed_text(memory_to_embedding_text(record)))

    async def recall(self, query: str, top_k: int = 3):
        return await self._repository.search(await self._embedding.embed_text(query), top_k)
