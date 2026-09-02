import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.memory.models import MemoryRecall


@dataclass(frozen=True)
class BenchmarkOutcome:
    expected_top1_memory_id: str
    ranked_memory_ids: list[str]


@dataclass(frozen=True)
class BenchmarkSummary:
    total: int
    top1_correct: int
    top3_hits: int
    top1_accuracy: float
    top3_hit_rate: float


def summarize_benchmark(outcomes: Sequence[BenchmarkOutcome]) -> BenchmarkSummary:
    if not outcomes:
        raise ValueError("Memory benchmark requires at least one outcome.")
    top1_correct = sum(
        1 for outcome in outcomes if outcome.ranked_memory_ids and outcome.ranked_memory_ids[0] == outcome.expected_top1_memory_id
    )
    top3_hits = sum(1 for outcome in outcomes if outcome.expected_top1_memory_id in outcome.ranked_memory_ids[:3])
    total = len(outcomes)
    return BenchmarkSummary(total, top1_correct, top3_hits, top1_correct / total, top3_hits / total)


def evaluate_query(
    query_id: str,
    query_text: str,
    expected_top1: str,
    recalls: Sequence[MemoryRecall],
) -> dict[str, object]:
    actual_top1 = recalls[0].memory_id if recalls else None
    return {
        "query_id": query_id,
        "query_text": query_text,
        "expected_top1": expected_top1,
        "actual_top1": actual_top1,
        "top1_score": recalls[0].similarity_score if recalls else None,
        "top3_ids": [recall.memory_id for recall in recalls[:3]],
        "correct": actual_top1 == expected_top1,
    }


def write_query_results_csv(path: Path, results: Sequence[dict[str, object]]) -> None:
    fields = ("query_id", "query_text", "expected_top1", "actual_top1", "top1_score", "top3_ids", "correct")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            row = {field: result.get(field) for field in fields}
            top3_ids = row["top3_ids"]
            row["top3_ids"] = "|".join(str(value) for value in top3_ids) if isinstance(top3_ids, list) else ""
            writer.writerow(row)
