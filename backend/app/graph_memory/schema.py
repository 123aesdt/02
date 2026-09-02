from typing import Protocol

from neo4j import Query
from neo4j.exceptions import Neo4jError

from app.graph_memory.protocols import GraphMemoryError

GRAPH_SCHEMA_STATEMENTS = (
    "CREATE CONSTRAINT graph_entity_key_unique IF NOT EXISTS FOR (n:GraphEntity) REQUIRE n.entity_key IS UNIQUE",
    "CREATE INDEX graph_entity_id_index IF NOT EXISTS FOR (n:GraphEntity) ON (n.entity_id)",
    "CREATE INDEX graph_entity_type_index IF NOT EXISTS FOR (n:GraphEntity) ON (n.entity_type)",
)


class QueryDriver(Protocol):
    async def execute_query(self, query: object, **kwargs: object) -> object: ...


async def bootstrap_graph_schema(
    driver: QueryDriver,
    database: str,
    *,
    query_timeout_seconds: float = 2.0,
) -> None:
    try:
        for statement in GRAPH_SCHEMA_STATEMENTS:
            await driver.execute_query(Query(statement, timeout=query_timeout_seconds), database_=database)
    except Neo4jError as error:
        raise GraphMemoryError("Graph schema bootstrap failed.") from error
