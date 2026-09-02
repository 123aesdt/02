import json
from collections.abc import Mapping, Sequence
from typing import Any

from neo4j import Query
from neo4j.exceptions import DriverError, Neo4jError

from app.graph_memory.models import EntityType, GraphEntity, GraphPath, GraphRelation, RelationType
from app.graph_memory.protocols import GraphMemoryError


class Neo4jGraphMemoryRepository:
    def __init__(self, driver: object, database: str, *, query_timeout_seconds: float = 1.0) -> None:
        if query_timeout_seconds <= 0:
            raise ValueError("query_timeout_seconds must be positive")
        self._driver = driver
        self._database = database
        self._query_timeout_seconds = query_timeout_seconds

    async def upsert_entity(self, entity: GraphEntity) -> None:
        label = EntityType(entity.entity_type).value
        query = f"""
        MERGE (n:GraphEntity:{label} {{entity_key: $entity_key}})
        ON CREATE SET n.created_at = datetime()
        SET n.entity_type = $entity_type,
            n.entity_id = $entity_id,
            n.display_name = $display_name,
            n.properties_json = $properties_json,
            n.updated_at = datetime()
        """
        await self._execute(
            query,
            {
                "entity_key": entity.entity_key,
                "entity_type": entity.entity_type.value,
                "entity_id": entity.entity_id,
                "display_name": entity.display_name,
                "properties_json": json.dumps(entity.properties, ensure_ascii=False, sort_keys=True),
            },
        )

    async def upsert_relation(self, relation: GraphRelation) -> None:
        relation_type = RelationType(relation.relation_type).value
        query = f"""
        MATCH (source:GraphEntity {{entity_key: $source_key}})
        MATCH (target:GraphEntity {{entity_key: $target_key}})
        MERGE (source)-[r:{relation_type}]->(target)
        SET r.confidence = $confidence,
            r.source_type = $source_type,
            r.evidence = $evidence,
            r.version = $version,
            r.timestamp = $timestamp,
            r.relation_key = $relation_key
        """
        await self._execute(
            query,
            {
                "source_key": relation.source.entity_key,
                "target_key": relation.target.entity_key,
                "confidence": relation.confidence,
                "source_type": relation.source_type,
                "evidence": relation.evidence,
                "version": relation.version,
                "timestamp": relation.timestamp,
                "relation_key": relation.relation_key,
            },
        )

    async def get_entity(self, entity_type: str, entity_id: str) -> GraphEntity | None:
        validated_type = EntityType(entity_type)
        records = await self._execute(
            """
            MATCH (n:GraphEntity {entity_type: $entity_type, entity_id: $entity_id})
            RETURN n { .entity_type, .entity_id, .display_name, .properties_json } AS entity
            LIMIT 1
            """,
            {"entity_type": validated_type.value, "entity_id": entity_id},
        )
        return self._entity(records[0]["entity"]) if records else None

    async def find_related(self, entity_keys: Sequence[str], *, limit: int) -> list[GraphRelation]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        records = await self._execute(
            """
            MATCH (anchor:GraphEntity)-[r]-(neighbor:GraphEntity)
            WHERE anchor.entity_key IN $entity_keys OR neighbor.entity_key IN $entity_keys
            WITH anchor, neighbor, r
            WHERE (r.projection_status IS NULL OR r.projection_status = $active_status)
              AND (r.expires_at IS NULL OR datetime(r.expires_at) > datetime())
            WITH DISTINCT r, startNode(r) AS source, endNode(r) AS target
            RETURN source { .entity_type, .entity_id, .display_name, .properties_json } AS source,
                   target { .entity_type, .entity_id, .display_name, .properties_json } AS target,
                   type(r) AS relation_type,
                   r { .confidence, .source_type, .evidence, .version, .timestamp } AS relation
            ORDER BY source.entity_key, relation_type, target.entity_key
            LIMIT $limit
            """,
            {"entity_keys": list(entity_keys), "active_status": "ACTIVE", "limit": limit},
        )
        return [
            self._relation(record["source"], record["target"], record["relation_type"], record["relation"])
            for record in records
        ]

    async def find_paths(self, start_key: str, *, max_hops: int, limit: int) -> list[GraphPath]:
        if not 1 <= max_hops <= 3:
            raise ValueError("max_hops must be between 1 and 3")
        if limit <= 0:
            raise ValueError("limit must be positive")
        query = f"""
        MATCH p=(start:GraphEntity {{entity_key: $start_key}})-[*1..{max_hops}]-(related:GraphEntity)
        WHERE all(n IN nodes(p) WHERE single(m IN nodes(p) WHERE m = n))
          AND all(r IN relationships(p) WHERE
              (r.projection_status IS NULL OR r.projection_status = $active_status)
              AND (r.expires_at IS NULL OR datetime(r.expires_at) > datetime()))
        RETURN [n IN nodes(p) | n {{ .entity_type, .entity_id, .display_name, .properties_json }}] AS entities,
               [r IN relationships(p) | {{
                   source_key: startNode(r).entity_key,
                   target_key: endNode(r).entity_key,
                   relation_type: type(r),
                   confidence: r.confidence,
                   source_type: r.source_type,
                   evidence: r.evidence,
                   version: r.version,
                   timestamp: r.timestamp
               }}] AS relations
        LIMIT $limit
        """
        records = await self._execute(
            query,
            {"start_key": start_key, "active_status": "ACTIVE", "limit": limit},
        )
        return [self._path(record) for record in records]

    async def _execute(self, query: str, parameters: Mapping[str, object]) -> list[Mapping[str, Any]]:
        try:
            records, _, _ = await self._driver.execute_query(
                Query(query, timeout=self._query_timeout_seconds),
                parameters_=dict(parameters),
                database_=self._database,
            )
            return list(records)
        except (DriverError, Neo4jError) as error:
            raise GraphMemoryError("Graph memory store operation failed.") from error

    @staticmethod
    def _entity(value: Mapping[str, Any]) -> GraphEntity:
        properties_value = value.get("properties_json") or "{}"
        properties = json.loads(properties_value) if isinstance(properties_value, str) else {}
        return GraphEntity(value["entity_type"], value["entity_id"], value["display_name"], properties)

    @classmethod
    def _relation(
        cls,
        source_value: Mapping[str, Any],
        target_value: Mapping[str, Any],
        relation_type: str,
        relation_value: Mapping[str, Any],
    ) -> GraphRelation:
        return GraphRelation(
            cls._entity(source_value),
            relation_type,
            cls._entity(target_value),
            confidence=float(relation_value.get("confidence") or 1.0),
            source_type=str(relation_value.get("source_type") or "graph"),
            evidence=relation_value.get("evidence"),
            version=int(relation_value.get("version") or 1),
            timestamp=str(relation_value.get("timestamp") or ""),
        )

    @classmethod
    def _path(cls, record: Mapping[str, Any]) -> GraphPath:
        entities = tuple(cls._entity(item) for item in record["entities"])
        by_key = {entity.entity_key: entity for entity in entities}
        relations = tuple(
            GraphRelation(
                by_key[item["source_key"]],
                item["relation_type"],
                by_key[item["target_key"]],
                confidence=float(item.get("confidence") or 1.0),
                source_type=str(item.get("source_type") or "graph"),
                evidence=item.get("evidence"),
                version=int(item.get("version") or 1),
                timestamp=str(item.get("timestamp") or ""),
            )
            for item in record["relations"]
        )
        return GraphPath(entities, relations)
