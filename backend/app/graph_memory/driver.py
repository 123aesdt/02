"""Official Neo4j driver factory with a bounded graph-memory retry policy."""

from neo4j import AsyncGraphDatabase

from app.core.config import Settings


def build_neo4j_driver(settings: Settings) -> object | None:
    if settings.graph_memory_backend != "neo4j":
        return None
    return AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        max_transaction_retry_time=0,
    )
