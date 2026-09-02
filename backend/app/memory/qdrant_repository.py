from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from app.memory.models import MemoryRecall, MemoryRecord


class EmbeddingDimensionError(ValueError):
    pass


class QdrantMemoryRepository:
    def __init__(self, client: QdrantClient, collection_name: str, vector_dimension: int) -> None:
        self._client, self._collection, self._dimension = client, collection_name, vector_dimension

    def ensure_collection(self) -> None:
        if not self._client.collection_exists(self._collection):
            self._client.create_collection(self._collection, vectors_config=models.VectorParams(size=self._dimension, distance=models.Distance.COSINE))

    async def upsert(self, record: MemoryRecord, vector: list[float]) -> None:
        if len(vector) != self._dimension:
            raise EmbeddingDimensionError(f"expected {self._dimension} dimensions")
        self.ensure_collection()
        payload = {
            "memory_id": record.memory_id,
            "driver_id": record.driver_id,
            "route_id": record.route_id,
            "anomaly_type": record.anomaly_type,
            "resolution_text": record.resolution_text,
            "metadata": record.metadata,
            "created_at": record.created_at.isoformat(),
        }
        if record.metadata.get("data_provenance") in {"DEMO", "LIVE"}:
            payload["data_provenance"] = record.metadata["data_provenance"]
        point_id = str(uuid5(NAMESPACE_URL, f"countyflow-memory:{record.memory_id}"))
        self._client.upsert(self._collection, [models.PointStruct(id=point_id, vector=vector, payload=payload)])

    async def search(self, vector: list[float], top_k: int) -> list[MemoryRecall]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        self.ensure_collection()
        active_or_legacy = models.Filter(
            should=[
                models.FieldCondition(
                    key="projection_status",
                    match=models.MatchValue(value="ACTIVE"),
                ),
                models.IsEmptyCondition(is_empty=models.PayloadField(key="projection_status")),
            ]
        )
        unexpired_or_legacy = models.Filter(
            should=[
                models.FieldCondition(
                    key="expires_at",
                    range=models.DatetimeRange(gt=datetime.now(UTC)),
                ),
                models.IsEmptyCondition(is_empty=models.PayloadField(key="expires_at")),
            ]
        )
        points = self._client.query_points(
            self._collection,
            query=vector,
            query_filter=models.Filter(must=[active_or_legacy, unexpired_or_legacy]),
            limit=top_k,
        ).points
        return [
            MemoryRecall(
                p.payload["memory_id"],
                p.score,
                p.payload["driver_id"],
                p.payload["route_id"],
                p.payload["anomaly_type"],
                p.payload["resolution_text"],
                p.payload["metadata"],
            )
            for p in points
        ]
