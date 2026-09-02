import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.acceptance.memory_benchmark import BenchmarkOutcome, evaluate_query, summarize_benchmark, write_query_results_csv
from app.memory.models import MemoryRecall

PROJECT_ROOT = Path(__file__).parents[3]
DATASET_ROOT = PROJECT_ROOT / "benchmarks" / "memory"


def load(name: str) -> list[dict[str, object]]:
    return json.loads((DATASET_ROOT / name).read_text(encoding="utf-8"))


def test_memory_benchmark_has_fifty_diverse_explicitly_labeled_queries():
    memories = load("memories.json")
    queries = load("queries.json")

    memory_ids = {str(memory["memory_id"]) for memory in memories}
    expected_ids = {str(query["expected_top1_memory_id"]) for query in queries}

    assert len(queries) >= 50
    assert len(memories) >= 10
    assert expected_ids == memory_ids
    assert len({str(query["category"]) for query in queries}) >= 5
    assert all(str(query["query"]).strip() for query in queries)


def test_memory_benchmark_reports_top1_and_top3_from_ranked_results():
    outcomes = [
        BenchmarkOutcome("memory-a", ["memory-a", "memory-b", "memory-c"]),
        BenchmarkOutcome("memory-b", ["memory-a", "memory-b", "memory-c"]),
        BenchmarkOutcome("memory-c", ["memory-a", "memory-b", "memory-d"]),
        BenchmarkOutcome("memory-d", []),
    ]

    summary = summarize_benchmark(outcomes)

    assert summary.total == 4
    assert summary.top1_correct == 1
    assert summary.top3_hits == 2
    assert summary.top1_accuracy == 0.25
    assert summary.top3_hit_rate == 0.5


def test_memory_benchmark_records_auditable_query_result_with_score():
    recalls = [
        MemoryRecall("memory-rain-li", 0.9134, "driver-li", "xinping-road", "rain", "reroute", {}),
        MemoryRecall("memory-fog-chen", 0.8123, "driver-chen", "river-road", "fog", "slow", {}),
    ]

    result = evaluate_query("query-001", "雨天新平路如何绕行", "memory-rain-li", recalls)

    assert result == {
        "query_id": "query-001",
        "query_text": "雨天新平路如何绕行",
        "expected_top1": "memory-rain-li",
        "actual_top1": "memory-rain-li",
        "top1_score": 0.9134,
        "top3_ids": ["memory-rain-li", "memory-fog-chen"],
        "correct": True,
    }


def test_memory_benchmark_writes_query_results_csv():
    with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
        output = Path(temporary_directory) / "results.csv"
        write_query_results_csv(
            output,
            [
                {
                    "query_id": "query-001",
                    "query_text": "雨天新平路如何绕行",
                    "expected_top1": "memory-rain-li",
                    "actual_top1": "memory-rain-li",
                    "top1_score": 0.9134,
                    "top3_ids": ["memory-rain-li", "memory-fog-chen"],
                    "correct": True,
                }
            ],
        )
        rows = output.read_text(encoding="utf-8").splitlines()
    assert rows[0] == "query_id,query_text,expected_top1,actual_top1,top1_score,top3_ids,correct"
    assert "query-001" in rows[1]
    assert "memory-rain-li|memory-fog-chen" in rows[1]


def test_memory_adoption_dataset_has_valid_and_invalid_expected_behaviors():
    cases = load("adoption_cases.json")
    valid = [case for case in cases if case["valid"] is True]
    invalid = [case for case in cases if case["valid"] is False]

    assert len(valid) >= 4
    assert len(invalid) >= 3
    assert all(case["expected_adopted"] is True for case in valid)
    assert all(case["expected_adopted"] is False for case in invalid)
