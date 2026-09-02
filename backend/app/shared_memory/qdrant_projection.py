import asyncio
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from app.shared_memory.protocols import VectorProjection


class QdrantMemoryProjection:
    def __init__(self, client: QdrantClient, collection_name: str, vector_dimension: int) -> None:
        self._client = client
        self._collection = collection_name
        self._dimension = vector_dimension

    def _ensure_collection(self) -> None:
        if not self._client.collection_exists(self._collection):
            self._client.create_collection(
                self._collection,
                vectors_config=models.VectorParams(
                    size=self._dimension,
                    distance=models.Distance.COSINE,
                ),
            )

    @staticmethod
    def point_id(projection: VectorProjection) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                f"countyflow-shared-memory:{projection.memory_id}:v{projection.control_version}",
            )
        )

    def _stage_sync(self, projection: VectorProjection) -> None:
        if len(projection.vector) != self._dimension:
            raise ValueError(f"expected {self._dimension} dimensions")
        self._ensure_collection()
        self._client.upsert(
            self._collection,
            [
                models.PointStruct(
                    id=self.point_id(projection),
                    vector=list(projection.vector),
                    payload={
                        "memory_id": projection.memory_id,
                        "driver_id": projection.driver_id,
                        "route_id": projection.route_id,
                        "anomaly_type": projection.anomaly_type,
                        "resolution_text": projection.resolution_text,
                        "metadata": dict(projection.metadata),
                        "created_at": projection.timestamp.isoformat()
                        if hasattr(projection, "timestamp")
                        else "",
                        "fact_key": projection.fact_key,
                        "control_version": projection.control_version,
                        "projection_status": "STAGED",
                        "mutation_id": projection.mutation_id,
                        "expires_at": (
                            projection.expires_at.isoformat() if projection.expires_at else None
                        ),
                    },
                )
            ],
            wait=True,
        )

    async def stage(self, projection: VectorProjection) -> None:
        await asyncio.to_thread(self._stage_sync, projection)

    def _probe_sync(self, mutation_id: str, control_version: int) -> str | None:
        self._ensure_collection()
        points, _ = self._client.scroll(
            self._collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="mutation_id",
                        match=models.MatchValue(value=mutation_id),
                    ),
                    models.FieldCondition(
                        key="control_version",
                        match=models.MatchValue(value=control_version),
                    ),
                ]
            ),
            limit=2,
            with_payload=True,
        )
        if not points:
            return None
        return str(points[0].payload.get("projection_status"))

    async def probe(self, mutation_id: str, control_version: int) -> str | None:
        return await asyncio.to_thread(self._probe_sync, mutation_id, control_version)

    def _activate_sync(self, projection: VectorProjection) -> None:
        self._ensure_collection()
        self._client.set_payload(
            self._collection,
            {"projection_status": "ACTIVE"},
            points=[self.point_id(projection)],
            wait=True,
        )

    async def activate(self, projection: VectorProjection) -> None:
        await asyncio.to_thread(self._activate_sync, projection)

    def _retire_previous_sync(self, projection: VectorProjection) -> None:
        self._ensure_collection()
        self._client.set_payload(
            self._collection,
            {"projection_status": "RETIRED"},
            points=models.Filter(
                must=[
                    models.FieldCondition(
                        key="fact_key",
                        match=models.MatchValue(value=projection.fact_key),
                    ),
                    models.FieldCondition(
                        key="projection_status",
                        match=models.MatchValue(value="ACTIVE"),
                    ),
                    models.FieldCondition(
                        key="control_version",
                        range=models.Range(lt=projection.control_version),
                    ),
                ]
            ),
            wait=True,
        )

    async def retire_previous(self, projection: VectorProjection) -> None:
        await asyncio.to_thread(self._retire_previous_sync, projection)

    def _count_points_sync(self, memory_id: str, *, version: int) -> int:
        self._ensure_collection()
        count = self._client.count(
            self._collection,
            count_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="memory_id",
                        match=models.MatchValue(value=memory_id),
                    ),
                    models.FieldCondition(
                        key="control_version",
                        match=models.MatchValue(value=version),
                    ),
                ]
            ),
            exact=True,
        )
        return count.count

    async def count_points(self, memory_id: str, *, version: int) -> int:
        return await asyncio.to_thread(self._count_points_sync, memory_id, version=version)
