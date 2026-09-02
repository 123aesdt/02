"""Resume one real shared-memory mutation after an acceptance fault injection."""

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from neo4j import AsyncGraphDatabase
from qdrant_client import QdrantClient
from redis.asyncio import Redis

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.database import build_session_factory
from app.events.broker import InMemoryTaskEventBroker
from app.providers.embedding.fake import FakeEmbeddingProvider
from app.shared_memory.events import MemoryMutationEventPublisher
from app.shared_memory.neo4j_projection import Neo4jMemoryProjection
from app.shared_memory.policy import MemoryPolicySettings
from app.shared_memory.projection_builder import DefaultMemoryProjectionBuilder
from app.shared_memory.qdrant_projection import QdrantMemoryProjection
from app.shared_memory.redis_lock import MemoryMutationLock
from app.shared_memory.service import SharedMemoryMutationService
from app.shared_memory.sqlalchemy_repository import SqlAlchemyMemoryControlRepository


async def run(mutation_id: str, database_url: str) -> dict[str, object]:
    redis_client = Redis.from_url("redis://127.0.0.1:6380/0", decode_responses=False)
    qdrant = QdrantClient(url="http://127.0.0.1:6333", check_compatibility=False)
    password = os.environ.get("NEO4J_PASSWORD", "")
    if not password:
        raise RuntimeError("NEO4J_PASSWORD is required")
    neo4j = AsyncGraphDatabase.driver(
        "bolt://127.0.0.1:7687",
        auth=(os.environ.get("NEO4J_USER", "neo4j"), password),
    )
    try:
        service = SharedMemoryMutationService(
            repository=SqlAlchemyMemoryControlRepository(build_session_factory(database_url)),
            lock=MemoryMutationLock(redis_client, ttl_ms=10_000),
            policy_settings=MemoryPolicySettings(Decimal("0.7500"), Decimal("0.1500")),
            vector_projection=QdrantMemoryProjection(qdrant, "entity_resolution_memory", 128),
            graph_projection=Neo4jMemoryProjection(neo4j, "neo4j", query_timeout_seconds=5.0),
            projection_builder=DefaultMemoryProjectionBuilder(FakeEmbeddingProvider(dimension=128)),
            event_publisher=MemoryMutationEventPublisher(InMemoryTaskEventBroker()),
            clock=lambda: datetime.now(UTC),
            timeout_seconds=15.0,
        )
        result = await service.resume_mutation(mutation_id)
        return result.to_dict()
    finally:
        await neo4j.close()
        qdrant.close()
        await redis_client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mutation-id", required=True)
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    result = asyncio.run(run(args.mutation_id, args.database_url))
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] != "APPLIED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
