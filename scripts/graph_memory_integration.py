import argparse
import asyncio
import json
import os
import statistics
import sys
from pathlib import Path
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.graph_memory.extractor import (
    DeterministicGraphTripleExtractor,
    GraphMemoryContext,
)
from app.graph_memory.neo4j_repository import Neo4jGraphMemoryRepository
from app.graph_memory.schema import bootstrap_graph_schema
from app.graph_memory.seed import development_seed, seed_graph_memory
from app.graph_memory.service import GraphMemoryService
from neo4j import AsyncGraphDatabase


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate seed idempotency and 20 warm Neo4j graph-memory queries.")
    parser.add_argument("--warm-queries", type=int, default=20)
    return parser.parse_args()


async def run(warm_queries: int) -> dict[str, object]:
    if warm_queries < 1:
        raise ValueError("warm_queries must be positive")
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "")
    database = os.environ.get("NEO4J_DATABASE", "neo4j")
    if not password:
        raise RuntimeError("NEO4J_PASSWORD is required")

    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    try:
        await driver.verify_connectivity()
        await bootstrap_graph_schema(driver, database)
        repository = Neo4jGraphMemoryRepository(driver, database)
        seed_entities, _ = development_seed()
        seed_entity_keys = [entity.entity_key for entity in seed_entities]
        await seed_graph_memory(repository)
        first_counts = await _counts(driver, database, seed_entity_keys)
        await seed_graph_memory(repository)
        second_counts = await _counts(driver, database, seed_entity_keys)
        if first_counts != second_counts or second_counts != (7, 5):
            raise AssertionError(f"Seed is not idempotent: first={first_counts}, second={second_counts}")

        service = GraphMemoryService(repository, DeterministicGraphTripleExtractor())
        context = GraphMemoryContext(
            driver_id="driver-li",
            vehicle_id="vehicle-cold-a",
            route_id="xinping-road",
            anomaly_type="rain_slippery",
            text="李师傅驾驶冷链车A，在雨天经过新平路时报告道路湿滑。",
        )
        recall = await service.recall(context)
        fact_ids = {(fact.source.entity_id, fact.relation_type.value, fact.target.entity_id) for fact in recall.facts}
        required = {
            ("driver-li", "HAS_RISK_ON", "xinping-road"),
            ("xinping-road", "HIGH_RISK_WHEN", "rain"),
            ("national-102", "ALTERNATIVE_TO", "xinping-road"),
        }
        if not required.issubset(fact_ids):
            raise AssertionError(f"Required graph facts were not recalled: {sorted(required - fact_ids)}")
        path_ids = {tuple(entity.entity_id for entity in path.entities) for path in recall.paths}
        required_path = ("driver-li", "xinping-road", "national-102")
        if required_path not in path_ids:
            raise AssertionError(f"Required two-hop graph path was not recalled: {required_path}")

        timings: list[float] = []
        for _ in range(warm_queries):
            started = perf_counter()
            await service.recall(context)
            timings.append((perf_counter() - started) * 1000)
        ordered = sorted(timings)
        p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))
        return {
            "neo4j": "verified",
            "entities": second_counts[0],
            "relations": second_counts[1],
            "required_facts": sorted("|".join(item) for item in required),
            "required_path": ">".join(required_path),
            "warm_queries": warm_queries,
            "timing_ms": {
                "min": round(min(timings), 3),
                "avg": round(statistics.fmean(timings), 3),
                "p95": round(ordered[p95_index], 3),
                "max": round(max(timings), 3),
            },
        }
    finally:
        await driver.close()


async def _counts(driver: object, database: str, entity_keys: list[str]) -> tuple[int, int]:
    entity_result = await driver.execute_query(
        "MATCH (n:GraphEntity) WHERE n.entity_key IN $entity_keys RETURN count(n) AS count",
        entity_keys=entity_keys,
        database_=database,
    )
    relation_result = await driver.execute_query(
        "MATCH (:GraphEntity)-[r]->(:GraphEntity) WHERE r.source_type = 'development_seed' RETURN count(r) AS count",
        database_=database,
    )
    return int(entity_result.records[0]["count"]), int(relation_result.records[0]["count"])


def main() -> None:
    args = parse_args()
    print(json.dumps(asyncio.run(run(args.warm_queries)), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
