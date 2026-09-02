"""Run the Phase 5B memory benchmark through an EmbeddingProvider and real Qdrant."""

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from app.acceptance.memory_benchmark import (
    BenchmarkOutcome,
    evaluate_query,
    summarize_benchmark,
    write_query_results_csv,
)
from app.acceptance.real_embedding_handoff import (
    RealEmbeddingConfigurationError,
    RealEmbeddingResultError,
    build_v2e_result,
    validate_real_embedding_configuration,
    write_result,
    write_v2e_reports,
)
from app.memory.models import MemoryRecord
from app.memory.qdrant_repository import QdrantMemoryRepository
from app.memory.service import EntityMemoryService
from app.providers.embedding.fake import FakeEmbeddingProvider
from app.providers.embedding.openai_compatible import OpenAICompatibleEmbeddingProvider
from app.routing.provider import InMemoryRouteProvider
from app.routing.service import RoutingService
from qdrant_client import QdrantClient

COLLECTION = "entity_resolution_memory_benchmark"


def load(path: Path) -> list[dict[str, object]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise TypeError(f"Benchmark file must contain an array: {path}")
    return value


def configured_provider(*, require_real: bool = False, qdrant_url: str = "http://localhost:6333") -> tuple[object, str, bool]:
    if require_real:
        configuration = validate_real_embedding_configuration(os.environ, qdrant_url)
        return (
            OpenAICompatibleEmbeddingProvider(
                configuration.base_url,
                configuration.api_key,
                configuration.model,
                configuration.dimension,
            ),
            "openai-compatible-real",
            True,
        )
    base_url = os.environ.get("EMBEDDING_BASE_URL", "").strip()
    api_key = os.environ.get("EMBEDDING_API_KEY", "").strip()
    model = os.environ.get("EMBEDDING_MODEL", "").strip()
    dimension = os.environ.get("EMBEDDING_DIMENSION", "").strip()
    if all((base_url, api_key, model, dimension)):
        return OpenAICompatibleEmbeddingProvider(base_url, api_key, model, int(dimension)), "openai-compatible-real", True
    return FakeEmbeddingProvider(dimension=128), "deterministic-functional-no-credential", False


async def adoption_results(cases: list[dict[str, object]]) -> dict[str, object]:
    service = RoutingService(InMemoryRouteProvider.default_catalog(), memory_adoption_threshold=0.75)
    results = []
    for case in cases:
        memory = {
            "memory_id": str(case["memory_id"]),
            "similarity_score": float(case["similarity_score"]),
            "driver_id": "benchmark-driver",
            "route_id": str(case["current_route_id"]),
            "anomaly_type": "benchmark",
            "historical_resolution": str(case["historical_resolution"]),
            "metadata": {},
        }
        capacity = {
            "driver_available": True,
            "vehicle_available": True,
            "load_ratio": 0.5,
            "station_load_ratio": 0.5,
            "capacity_status": str(case["capacity_status"]),
            "risk_level": "low",
            "reason": None,
            "provider_name": "benchmark",
        }
        routed = await service.route(
            str(case["current_route_id"]),
            [memory],
            "heavy_rain",
            str(case["road_condition"]),
            str(case["environment_risk"]),
            capacity,
        )
        expected = bool(case["expected_adopted"])
        results.append(
            {
                "case_id": case["case_id"],
                "valid": case["valid"],
                "expected_adopted": expected,
                "actual_adopted": routed.memory_adopted,
                "recommended_route": routed.recommended_route,
                "passed": routed.memory_adopted is expected,
            }
        )
    valid = [result for result in results if result["valid"] is True]
    invalid = [result for result in results if result["valid"] is False]
    return {
        "cases": results,
        "valid_sample_count": len(valid),
        "valid_adoption_rate": sum(1 for result in valid if result["actual_adopted"] is True) / len(valid),
        "invalid_sample_count": len(invalid),
        "invalid_adoption_rate": sum(1 for result in invalid if result["actual_adopted"] is True) / len(invalid),
        "passed": all(result["passed"] for result in results),
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, default=Path("benchmarks/memory"))
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path)
    parser.add_argument("--require-real", action="store_true")
    parser.add_argument("--final-report", type=Path)
    parser.add_argument("--vector-report", type=Path)
    args = parser.parse_args()

    memories = load(args.dataset_root / "memories.json")
    queries = load(args.dataset_root / "queries.json")
    cases = load(args.dataset_root / "adoption_cases.json")
    provider, provider_label, formal = configured_provider(require_real=args.require_real, qdrant_url=args.qdrant_url)
    dimension = int(provider.vector_dimension)
    client = QdrantClient(url=args.qdrant_url)
    client.get_collections()
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    service = EntityMemoryService(provider, QdrantMemoryRepository(client, COLLECTION, dimension))
    for memory in memories:
        await service.remember(
            MemoryRecord(
                memory_id=str(memory["memory_id"]),
                driver_id=str(memory["driver_id"]),
                route_id=str(memory["route_id"]),
                anomaly_type=str(memory["anomaly_type"]),
                resolution_text=str(memory["resolution_text"]),
                metadata={"text": str(memory["text"]), "category": str(memory["category"])},
                created_at=datetime.now(UTC),
            )
        )

    details = []
    outcomes = []
    for index, query in enumerate(queries, start=1):
        query_text = str(query["query"])
        recalls = await service.recall(query_text, top_k=3)
        ranked = [recall.memory_id for recall in recalls]
        expected = str(query["expected_top1_memory_id"])
        outcomes.append(BenchmarkOutcome(expected, ranked))
        details.append(evaluate_query(f"query-{index:03d}", query_text, expected, recalls))
    summary = summarize_benchmark(outcomes)
    adoption = await adoption_results(cases)
    collection_points = client.get_collection(COLLECTION).points_count
    client.close()

    payload = {
        "as_of": datetime.now(UTC).isoformat(),
        "provider": provider_label,
        "provider_base_host": urlparse(os.environ.get("EMBEDDING_BASE_URL", "")).hostname if formal else None,
        "model": os.environ.get("EMBEDDING_MODEL") if formal else None,
        "dimension": dimension,
        "formal_real_embedding": formal,
        "credential_status": "CONFIGURED" if formal else "REAL EMBEDDING BENCHMARK BLOCKED BY CREDENTIAL",
        "qdrant_url_kind": "server",
        "collection": COLLECTION,
        "collection_points": collection_points,
        "dataset_size": len(queries),
        "memory_count": len(memories),
        "top1_correct": summary.top1_correct if formal else None,
        "top1_accuracy": summary.top1_accuracy if formal else None,
        "top3_hits": summary.top3_hits if formal else None,
        "top3_hit_rate": summary.top3_hit_rate if formal else None,
        "functional_fake_results": None
        if formal
        else {
            "top1_correct": summary.top1_correct,
            "top1_accuracy": summary.top1_accuracy,
            "top3_hits": summary.top3_hits,
            "top3_hit_rate": summary.top3_hit_rate,
            "not_formal": not formal,
        },
        "failed_query_count": sum(not bool(detail["correct"]) for detail in details),
        "failed_queries": [detail for detail in details if not bool(detail["correct"])],
        "retrieval_representation": {
            "memory": "司机 {driver_id} 路线 {route_id} 异常 {anomaly_type} 解决方案 {resolution_text} {metadata.text}",
            "query": "raw benchmark query text",
            "ranking": "Qdrant cosine similarity Top-K without manual reranking",
        },
        "adoption": adoption,
        "queries": details,
    }
    v2e_result = build_v2e_result(payload) if args.require_real else None
    if v2e_result:
        payload.update(v2e_result)
    write_result(args.output, payload)
    write_query_results_csv(args.csv_output or args.output.with_suffix(".csv"), details)
    if v2e_result and args.final_report and args.vector_report:
        write_v2e_reports(v2e_result, args.final_report, args.vector_report)
    if v2e_result and v2e_result["passed"] is not True:
        raise RealEmbeddingResultError("Real embedding Top-1 result is below 46/50")
    print(json.dumps({key: payload[key] for key in payload if key not in {"queries"}}, ensure_ascii=False, indent=2))


def cli() -> int:
    try:
        asyncio.run(main())
    except RealEmbeddingConfigurationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except RealEmbeddingResultError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 4
    except Exception:  # noqa: BLE001 - the CLI must suppress provider exceptions that may contain request metadata
        print(
            "ERROR: Real embedding benchmark failed; sensitive provider and request details were suppressed.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
