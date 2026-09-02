import asyncio
import base64
import binascii
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from qdrant_client import QdrantClient, models

from app.workspace_reads.models import VectorMemoryListItem, VectorMemoryPage


class InvalidVectorMemoryCursor(ValueError):
    pass


class VectorMemoryReadUnavailable(RuntimeError):
    pass


class QdrantVectorMemoryReadRepository:
    def __init__(self, client: QdrantClient, collection_name: str) -> None:
        self._client = client
        self._collection = collection_name

    async def list_records(self, *, limit: int = 20, cursor: str | None = None) -> VectorMemoryPage:
        limit = self._validated_limit(limit)
        offset = self._decode_cursor(cursor)
        try:
            collection_exists = await asyncio.to_thread(self._client.collection_exists, self._collection)
            if not collection_exists:
                return VectorMemoryPage(items=(), total=0, next_cursor=None, vector_dimension=None)
            points, next_offset = await asyncio.to_thread(
                self._client.scroll,
                collection_name=self._collection,
                limit=limit,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            collection = await asyncio.to_thread(self._client.get_collection, self._collection)
            demo_count_result = await asyncio.to_thread(
                self._client.count,
                collection_name=self._collection,
                count_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="data_provenance",
                            match=models.MatchValue(value="DEMO"),
                        )
                    ]
                ),
                exact=True,
            )
        except Exception:
            raise VectorMemoryReadUnavailable("vector memory read unavailable") from None

        total = self._point_count(collection)
        demo_count = getattr(demo_count_result, "count", 0)
        return VectorMemoryPage(
            items=tuple(self._to_item(point.payload) for point in points),
            total=total,
            next_cursor=self._encode_cursor(next_offset) if next_offset is not None else None,
            vector_dimension=self._vector_dimension(collection),
            provenance=self._provenance(
                total=total,
                demo_count=demo_count if isinstance(demo_count, int) else 0,
            ),
        )

    @staticmethod
    def _validated_limit(limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        return limit

    @staticmethod
    def _encode_cursor(offset: object) -> str:
        payload = json.dumps(offset, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii")

    @staticmethod
    def _decode_cursor(cursor: str | None) -> int | str | None:
        if cursor is None:
            return None
        if not isinstance(cursor, str) or not cursor:
            raise InvalidVectorMemoryCursor("invalid vector memory cursor")
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            decoded = base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)
            offset = json.loads(decoded.decode("utf-8"))
        except (UnicodeEncodeError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError) as error:
            raise InvalidVectorMemoryCursor("invalid vector memory cursor") from error
        if isinstance(offset, bool) or not isinstance(offset, (int, str)) or (isinstance(offset, str) and not offset):
            raise InvalidVectorMemoryCursor("invalid vector memory cursor")
        return offset

    @staticmethod
    def _to_item(payload: object) -> VectorMemoryListItem:
        values = payload if isinstance(payload, Mapping) else {}
        return VectorMemoryListItem(
            memory_id=QdrantVectorMemoryReadRepository._string(values, "memory_id"),
            driver_id=QdrantVectorMemoryReadRepository._string(values, "driver_id"),
            route_id=QdrantVectorMemoryReadRepository._string(values, "route_id"),
            anomaly_type=QdrantVectorMemoryReadRepository._string(values, "anomaly_type"),
            historical_resolution=QdrantVectorMemoryReadRepository._string(values, "resolution_text"),
            created_at=QdrantVectorMemoryReadRepository._datetime(values.get("created_at")),
            projection_status=QdrantVectorMemoryReadRepository._string(values, "projection_status"),
        )

    @staticmethod
    def _string(values: Mapping[str, Any], key: str) -> str | None:
        value = values.get(key)
        return value if isinstance(value, str) else None

    @staticmethod
    def _datetime(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _point_count(collection: object) -> int:
        point_count = getattr(collection, "points_count", 0)
        return point_count if isinstance(point_count, int) else 0

    @staticmethod
    def _provenance(*, total: int, demo_count: int) -> str:
        if total > 0 and demo_count == total:
            return "DEMO"
        if demo_count > 0:
            return "MIXED"
        return "LIVE"

    @staticmethod
    def _vector_dimension(collection: object) -> int | None:
        config = getattr(collection, "config", None)
        params = getattr(config, "params", None)
        vectors = getattr(params, "vectors", None)
        if isinstance(vectors, Mapping):
            dimensions = {
                QdrantVectorMemoryReadRepository._configured_vector_size(vector)
                for vector in vectors.values()
            }
            dimensions.discard(None)
            return dimensions.pop() if len(dimensions) == 1 else None
        return QdrantVectorMemoryReadRepository._configured_vector_size(vectors)

    @staticmethod
    def _configured_vector_size(vector: object) -> int | None:
        dimension = vector.get("size") if isinstance(vector, Mapping) else getattr(vector, "size", None)
        return dimension if isinstance(dimension, int) and not isinstance(dimension, bool) else None
