from collections import deque
from collections.abc import Iterable, Sequence

from app.graph_memory.models import EntityType, GraphEntity, GraphPath, GraphRelation


class FakeGraphMemoryRepository:
    def __init__(self) -> None:
        self._entities: dict[str, GraphEntity] = {}
        self._relations: dict[str, GraphRelation] = {}

    def seed(self, entities: Iterable[GraphEntity], relations: Iterable[GraphRelation]) -> None:
        for entity in entities:
            self._entities[entity.entity_key] = entity
        for relation in relations:
            self._entities[relation.source.entity_key] = relation.source
            self._entities[relation.target.entity_key] = relation.target
            self._relations[relation.relation_key] = relation

    async def upsert_entity(self, entity: GraphEntity) -> None:
        self._entities[entity.entity_key] = entity

    async def upsert_relation(self, relation: GraphRelation) -> None:
        self.seed((relation.source, relation.target), (relation,))

    async def get_entity(self, entity_type: str, entity_id: str) -> GraphEntity | None:
        kind = EntityType(entity_type)
        return self._entities.get(f"{kind.value}:{entity_id}")

    async def find_related(self, entity_keys: Sequence[str], *, limit: int) -> list[GraphRelation]:
        keys = set(entity_keys)
        matches = [
            relation
            for relation in self._relations.values()
            if relation.source.entity_key in keys or relation.target.entity_key in keys
        ]
        return sorted(matches, key=lambda item: item.relation_key)[:limit]

    async def find_paths(self, start_key: str, *, max_hops: int, limit: int) -> list[GraphPath]:
        if not 1 <= max_hops <= 3:
            raise ValueError("max_hops must be between 1 and 3")
        if limit <= 0:
            raise ValueError("limit must be positive")
        if start_key not in self._entities:
            return []

        paths: list[GraphPath] = []
        queue = deque([(start_key, (self._entities[start_key],), tuple(), frozenset({start_key}))])
        while queue and len(paths) < limit:
            current_key, entities, relations, visited = queue.popleft()
            if relations:
                paths.append(GraphPath(entities, relations))
            if len(relations) == max_hops:
                continue
            for relation in sorted(self._relations.values(), key=lambda item: item.relation_key):
                if relation.source.entity_key == current_key:
                    next_entity = relation.target
                elif relation.target.entity_key == current_key:
                    next_entity = relation.source
                else:
                    continue
                if next_entity.entity_key in visited:
                    continue
                queue.append(
                    (
                        next_entity.entity_key,
                        (*entities, next_entity),
                        (*relations, relation),
                        visited | {next_entity.entity_key},
                    )
                )
        return paths[:limit]

    @property
    def entity_count(self) -> int:
        return len(self._entities)

    @property
    def relation_count(self) -> int:
        return len(self._relations)

