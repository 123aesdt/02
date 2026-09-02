from uuid import NAMESPACE_URL, uuid5

from neo4j import Query
from neo4j.exceptions import Neo4jError

from app.graph_memory.models import EntityType, RelationType
from app.shared_memory.protocols import GraphProjection


class Neo4jMemoryProjectionError(Exception):
    """Normalized graph projection failure without driver details."""


class Neo4jMemoryProjection:
    def __init__(
        self,
        driver: object,
        database: str,
        *,
        query_timeout_seconds: float = 1.0,
    ) -> None:
        if query_timeout_seconds <= 0:
            raise ValueError("query_timeout_seconds must be positive")
        self._driver = driver
        self._database = database
        self._query_timeout_seconds = query_timeout_seconds

    @staticmethod
    def projection_id(projection: GraphProjection) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                f"countyflow-shared-memory:{projection.fact_key}:v{projection.control_version}",
            )
        )

    async def stage(self, projection: GraphProjection) -> None:
        source_label = EntityType(projection.source.entity_type).value
        target_label = EntityType(projection.target.entity_type).value
        relation_type = RelationType(projection.relation_type).value
        await self._execute(
            f"""
            MERGE (n:GraphEntity:{source_label} {{entity_key: $entity_key}})
            SET n.entity_type = $entity_type,
                n.entity_id = $entity_id,
                n.display_name = $display_name,
                n.properties_json = $properties_json
            """,
            self._entity_parameters(projection.source),
        )
        await self._execute(
            f"""
            MERGE (n:GraphEntity:{target_label} {{entity_key: $entity_key}})
            SET n.entity_type = $entity_type,
                n.entity_id = $entity_id,
                n.display_name = $display_name,
                n.properties_json = $properties_json
            """,
            self._entity_parameters(projection.target),
        )
        await self._execute(
            f"""
            MATCH (source:GraphEntity {{entity_key: $source_key}})
            MATCH (target:GraphEntity {{entity_key: $target_key}})
            MERGE (source)-[r:{relation_type} {{projection_id: $projection_id}}]->(target)
            SET r.control_fact_key = $fact_key,
                r.control_version = $control_version,
                r.mutation_id = $mutation_id,
                r.projection_status = $staged_status,
                r.confidence = $confidence,
                r.source_type = $source_type,
                r.evidence = $evidence,
                r.expires_at = $expires_at,
                r.version = $control_version,
                r.timestamp = $timestamp
            """,
            {
                "source_key": projection.source.entity_key,
                "target_key": projection.target.entity_key,
                "projection_id": self.projection_id(projection),
                "fact_key": projection.fact_key,
                "control_version": projection.control_version,
                "mutation_id": projection.mutation_id,
                "staged_status": "STAGED",
                "confidence": float(projection.confidence),
                "source_type": projection.source_type,
                "evidence": projection.evidence,
                "expires_at": projection.expires_at.isoformat() if projection.expires_at else None,
                "timestamp": projection.timestamp.isoformat(),
            },
        )

    async def probe(self, mutation_id: str, control_version: int) -> str | None:
        records = await self._execute(
            """
            MATCH ()-[r]->()
            WHERE r.mutation_id = $mutation_id AND r.control_version = $control_version
            RETURN r.projection_status AS projection_status
            LIMIT 1
            """,
            {"mutation_id": mutation_id, "control_version": control_version},
        )
        if not records:
            return None
        return str(records[0]["projection_status"])

    async def activate(self, projection: GraphProjection) -> None:
        await self._execute(
            """
            MATCH ()-[r]->()
            WHERE r.projection_id = $projection_id
            SET r.projection_status = $active_status
            """,
            {"projection_id": self.projection_id(projection), "active_status": "ACTIVE"},
        )

    async def retire_previous(self, projection: GraphProjection) -> None:
        await self._execute(
            """
            MATCH ()-[r]->()
            WHERE r.control_fact_key = $fact_key
              AND r.projection_status = $active_status
              AND r.control_version < $control_version
            SET r.projection_status = $retired_status
            """,
            {
                "fact_key": projection.fact_key,
                "control_version": projection.control_version,
                "active_status": "ACTIVE",
                "retired_status": "RETIRED",
            },
        )

    async def count_edges(self, fact_key: str, *, version: int) -> int:
        records = await self._execute(
            """
            MATCH ()-[r]->()
            WHERE r.control_fact_key = $fact_key AND r.control_version = $control_version
            RETURN count(r) AS edge_count
            """,
            {"fact_key": fact_key, "control_version": version},
        )
        return int(records[0]["edge_count"]) if records else 0

    @staticmethod
    def _entity_parameters(entity: object) -> dict[str, object]:
        import json

        return {
            "entity_key": entity.entity_key,
            "entity_type": entity.entity_type.value,
            "entity_id": entity.entity_id,
            "display_name": entity.display_name,
            "properties_json": json.dumps(
                entity.properties,
                ensure_ascii=False,
                sort_keys=True,
            ),
        }

    async def _execute(self, query: str, parameters: dict[str, object]) -> list[dict[str, object]]:
        try:
            records, _, _ = await self._driver.execute_query(
                Query(query, timeout=self._query_timeout_seconds),
                parameters_=parameters,
                database_=self._database,
            )
            return list(records)
        except Neo4jError as error:
            raise Neo4jMemoryProjectionError("Neo4j memory projection operation failed") from error

