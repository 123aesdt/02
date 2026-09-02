import argparse
import asyncio
import csv
import json
import os
import statistics
import sys
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.acceptance.v2e import GraphAcceptanceCase, summarize_graph_acceptance
from app.graph_memory.extractor import (
    DeterministicGraphTripleExtractor,
    GraphMemoryContext,
)
from app.graph_memory.models import GraphEntity, GraphRelation
from app.graph_memory.neo4j_repository import Neo4jGraphMemoryRepository
from app.graph_memory.schema import bootstrap_graph_schema
from app.graph_memory.seed import seed_graph_memory
from neo4j import AsyncGraphDatabase


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the V2-E real Neo4j extraction, recall, and latency acceptance.")
    parser.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "benchmarks" / "graph" / "v2e_cases.json")
    parser.add_argument("--warm-queries", type=int, default=50)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--timings-csv", type=Path, required=True)
    return parser.parse_args()


async def run(dataset_path: Path, warm_queries: int) -> dict[str, object]:
    if warm_queries < 50:
        raise ValueError("V2-E requires at least 50 warm graph queries")
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    if len(dataset["queries"]) < 20:
        raise ValueError("V2-E graph dataset requires at least 20 query cases")

    password = os.environ.get("NEO4J_PASSWORD", "")
    if not password:
        raise RuntimeError("NEO4J_PASSWORD is required")
    database = os.environ.get("NEO4J_DATABASE", "neo4j")
    driver = AsyncGraphDatabase.driver(
        os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        auth=(os.environ.get("NEO4J_USER", "neo4j"), password),
    )
    try:
        await driver.verify_connectivity()
        await bootstrap_graph_schema(driver, database)
        repository = Neo4jGraphMemoryRepository(driver, database)
        await seed_graph_memory(repository)
        entities = {
            f"{item['type']}:{item['id']}": GraphEntity(item["type"], item["id"], item["name"], {"v2e": True})
            for item in dataset["entities"]
        }
        for entity in entities.values():
            await repository.upsert_entity(entity)
        for item in dataset["relations"]:
            await repository.upsert_relation(
                GraphRelation(
                    entities[item["source"]],
                    item["type"],
                    entities[item["target"]],
                    source_type=item["source_type"],
                    evidence="V2-E structured graph acceptance dataset",
                )
            )

        extraction_rows = await _run_extraction_cases(repository, dataset["extraction_cases"])
        query_rows, cases = await _run_query_cases(repository, dataset["queries"])
        warm_timings = await _warm_queries(repository, dataset["queries"], warm_queries)
        summary = summarize_graph_acceptance(cases, warm_timings_ms=warm_timings)
        entity_types = sorted({item["type"] for item in dataset["entities"]})
        relation_types = sorted({item["type"] for item in dataset["relations"]})
        required_entity_types = {
            "Driver",
            "Vehicle",
            "Route",
            "Weather",
            "RoadCondition",
            "Station",
            "Anomaly",
            "Resolution",
        }
        required_relation_types = {
            "DRIVES",
            "HAS_RISK_ON",
            "HIGH_RISK_WHEN",
            "ALTERNATIVE_TO",
            "STATUS",
            "RESOLVED_BY",
        }
        extraction_passed = all(row["entities_correct"] and row["relations_correct"] for row in extraction_rows)
        coverage_passed = required_entity_types.issubset(entity_types) and required_relation_types.issubset(relation_types)
        return {
            "passed": summary.passed and extraction_passed and coverage_passed,
            "real_neo4j": True,
            "dataset": str(dataset_path.relative_to(PROJECT_ROOT)),
            "coverage": {
                "entity_types": entity_types,
                "relation_types": relation_types,
                "passed": coverage_passed,
            },
            "extraction": {
                "cases": len(extraction_rows),
                "entity_correct": sum(bool(row["entities_correct"]) for row in extraction_rows),
                "relation_correct": sum(bool(row["relations_correct"]) for row in extraction_rows),
                "passed": extraction_passed,
                "results": extraction_rows,
            },
            "recall": {**asdict(summary), "results": query_rows},
            "timing_ms": {
                "min": round(min(warm_timings), 3),
                "avg": round(statistics.fmean(warm_timings), 3),
                "p95": round(summary.p95_ms, 3),
                "max": round(max(warm_timings), 3),
                "samples": [round(item, 3) for item in warm_timings],
            },
        }
    finally:
        await driver.close()


async def _run_extraction_cases(repository: object, raw_cases: list[dict[str, object]]) -> list[dict[str, object]]:
    extractor = DeterministicGraphTripleExtractor()
    results: list[dict[str, object]] = []
    for item in raw_cases:
        extraction = extractor.extract(
            GraphMemoryContext(
                driver_id=str(item["driver_id"]),
                vehicle_id=str(item["vehicle_id"]) if item.get("vehicle_id") else None,
                route_id=str(item["route_id"]),
                anomaly_type=str(item["anomaly_type"]),
                weather=str(item["weather"]) if item.get("weather") else None,
                text=str(item["text"]),
            )
        )
        for entity in extraction.entities:
            await repository.upsert_entity(entity)
        for relation in extraction.relations:
            await repository.upsert_relation(relation)
        actual_entities = sorted(entity.entity_key for entity in extraction.entities)
        actual_relations = sorted(relation.relation_key for relation in extraction.relations)
        expected_entities = sorted(str(value) for value in item["entities"])
        expected_relations = sorted(str(value) for value in item["relations"])
        results.append(
            {
                "case_id": item["id"],
                "input_text": item["text"],
                "expected_entities": expected_entities,
                "actual_entities": actual_entities,
                "entities_correct": actual_entities == expected_entities,
                "expected_relations": expected_relations,
                "actual_relations": actual_relations,
                "relations_correct": actual_relations == expected_relations,
                "persisted_to_neo4j": True,
            }
        )
    return results


async def _run_query_cases(
    repository: object,
    raw_cases: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[GraphAcceptanceCase]]:
    rows: list[dict[str, object]] = []
    cases: list[GraphAcceptanceCase] = []
    for item in raw_cases:
        started = perf_counter()
        facts = await repository.find_related([str(item["anchor"])], limit=25)
        paths = await repository.find_paths(str(item["anchor"]), max_hops=2, limit=25)
        elapsed_ms = (perf_counter() - started) * 1000
        actual_facts = tuple(
            (fact.source.entity_id, fact.relation_type.value, fact.target.entity_id) for fact in facts
        )
        actual_paths = tuple(tuple(entity.entity_id for entity in path.entities) for path in paths)
        expected_fact = tuple(str(value) for value in item["fact"])
        expected_path = tuple(str(value) for value in item["path"]) if item.get("path") else None
        case = GraphAcceptanceCase(
            query_id=str(item["id"]),
            expected_fact=expected_fact,
            actual_facts=actual_facts,
            expected_path=expected_path,
            actual_paths=actual_paths,
            elapsed_ms=elapsed_ms,
        )
        cases.append(case)
        rows.append(
            {
                "query_id": case.query_id,
                "anchor": item["anchor"],
                "expected_fact": "|".join(expected_fact),
                "fact_correct": case.fact_passed,
                "expected_path": ">".join(expected_path) if expected_path else "",
                "path_correct": case.path_passed,
                "elapsed_ms": round(elapsed_ms, 3),
            }
        )
    return rows, cases


async def _warm_queries(repository: object, raw_cases: list[dict[str, object]], count: int) -> list[float]:
    timings: list[float] = []
    for number in range(count):
        item = raw_cases[number % len(raw_cases)]
        started = perf_counter()
        await repository.find_related([str(item["anchor"])], limit=25)
        await repository.find_paths(str(item["anchor"]), max_hops=2, limit=25)
        timings.append((perf_counter() - started) * 1000)
    return timings


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    result = asyncio.run(run(args.dataset, args.warm_queries))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(args.csv, result["recall"]["results"])
    _write_csv(
        args.timings_csv,
        [{"sample": index, "elapsed_ms": elapsed} for index, elapsed in enumerate(result["timing_ms"]["samples"], 1)],
    )
    print(json.dumps({key: value for key, value in result.items() if key not in {"recall", "extraction"}}, ensure_ascii=False))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
