from time import perf_counter

from app.graph_memory.extractor import GraphMemoryContext
from app.graph_memory.models import GraphMemoryRecall, GraphPath, GraphRelation
from app.graph_memory.protocols import GraphMemoryRepository, GraphTripleExtractor


class GraphMemoryService:
    def __init__(
        self,
        repository: GraphMemoryRepository,
        extractor: GraphTripleExtractor,
        *,
        max_hops: int = 2,
        result_limit: int = 25,
    ) -> None:
        if not 1 <= max_hops <= 3:
            raise ValueError("max_hops must be between 1 and 3")
        if result_limit <= 0:
            raise ValueError("result_limit must be positive")
        self._repository = repository
        self._extractor = extractor
        self._max_hops = max_hops
        self._result_limit = result_limit

    async def recall(self, context: GraphMemoryContext) -> GraphMemoryRecall:
        started = perf_counter()
        extraction = self._extractor.extract(context)
        for entity in extraction.entities:
            await self._repository.upsert_entity(entity)
        for relation in extraction.relations:
            await self._repository.upsert_relation(relation)

        keys = [entity.entity_key for entity in extraction.entities]
        facts = await self._repository.find_related(keys, limit=self._result_limit)
        paths: list[GraphPath] = []
        seen_paths: set[tuple[str, ...]] = set()
        for key in keys:
            remaining = self._result_limit - len(paths)
            if remaining <= 0:
                break
            for path in await self._repository.find_paths(key, max_hops=self._max_hops, limit=remaining):
                identity = tuple(entity.entity_key for entity in path.entities)
                if identity not in seen_paths:
                    seen_paths.add(identity)
                    paths.append(path)

        unique_facts: dict[str, GraphRelation] = {fact.relation_key: fact for fact in facts}
        return GraphMemoryRecall(
            extraction.entities,
            tuple(unique_facts.values()),
            tuple(paths[: self._result_limit]),
            elapsed_ms=(perf_counter() - started) * 1000,
        )
