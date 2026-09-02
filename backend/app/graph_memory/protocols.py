from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.graph_memory.models import GraphEntity, GraphPath, GraphRelation


class GraphMemoryError(Exception):
    """Safe graph-store failure exposed to the service and agent boundary."""


@runtime_checkable
class GraphMemoryRepository(Protocol):
    async def upsert_entity(self, entity: GraphEntity) -> None: ...

    async def upsert_relation(self, relation: GraphRelation) -> None: ...

    async def get_entity(self, entity_type: str, entity_id: str) -> GraphEntity | None: ...

    async def find_related(self, entity_keys: Sequence[str], *, limit: int) -> list[GraphRelation]: ...

    async def find_paths(self, start_key: str, *, max_hops: int, limit: int) -> list[GraphPath]: ...


class GraphTripleExtractor(Protocol):
    def extract(self, context: object) -> object: ...

