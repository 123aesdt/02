from app.graph_memory.models import EntityType, GraphEntity, RelationType
from app.providers.embedding.base import EmbeddingProvider
from app.shared_memory.identity import canonical_json
from app.shared_memory.protocols import GraphProjection, VectorProjection


class DefaultMemoryProjectionBuilder:
    def __init__(self, embedding_provider: EmbeddingProvider) -> None:
        self._embedding = embedding_provider

    async def build_vector(
        self,
        command,
        mutation_id: str,
        fact_key: str,
        version: int,
    ) -> VectorProjection:
        text = " ".join(
            part
            for part in (
                command.subject_id,
                command.object_id,
                command.predicate,
                canonical_json(command.value_json),
                command.evidence_text,
                command.reason,
            )
            if part
        )
        vector = await self._embedding.embed_text(text)
        return VectorProjection(
            mutation_id=mutation_id,
            fact_key=fact_key,
            control_version=version,
            memory_id=command.vector_memory_id or fact_key,
            vector=tuple(vector),
            driver_id=command.subject_id,
            route_id=command.object_id or "unknown-route",
            anomaly_type=command.predicate,
            resolution_text=str(command.value_json.get("resolution", command.value_json)),
            metadata={"text": text},
            expires_at=command.expires_at,
        )

    async def build_graph(
        self,
        command,
        mutation_id: str,
        fact_key: str,
        version: int,
    ) -> GraphProjection:
        value = next(iter(command.value_json.values()))
        target_type = (
            EntityType(command.object_type)
            if command.object_type
            else EntityType.ROAD_CONDITION
        )
        target_id = command.object_id or str(value).strip().lower()
        return GraphProjection(
            mutation_id=mutation_id,
            fact_key=fact_key,
            control_version=version,
            source=GraphEntity(
                EntityType(command.subject_type),
                command.subject_id,
                command.subject_id,
            ),
            relation_type=RelationType(command.predicate),
            target=GraphEntity(target_type, target_id, str(value)),
            confidence=command.confidence,
            source_type=command.source_type,
            evidence=command.evidence_text,
            expires_at=command.expires_at,
            timestamp=command.incoming_at,
        )
