"""Validate and summarize three V2-E Locust runs."""

import argparse
import csv
import json
from pathlib import Path


def rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["Name"]: row for row in csv.DictReader(handle)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-directory", type=Path, default=Path("docs/verification/v2-e/raw"))
    parser.add_argument("--output", type=Path, default=Path("docs/verification/v2-e/raw/locust-results.json"))
    args = parser.parse_args()
    runs = []
    for number in range(1, 4):
        path = args.raw_directory / f"locust-v2e-run-{number}_stats.csv"
        data = rows(path)
        aggregate = data["Aggregated"]
        request_count = int(aggregate["Request Count"])
        failures = int(aggregate["Failure Count"])
        graph = data["Neo4j bounded graph query"]
        record = {
            "run": number,
            "duration_seconds": 60,
            "users": 50,
            "spawn_rate_per_second": 25,
            "requests": request_count,
            "failures": failures,
            "qps": round(float(aggregate["Requests/s"]), 3),
            "p50_ms": float(aggregate["50%"]),
            "p95_ms": float(aggregate["95%"]),
            "p99_ms": float(aggregate["99%"]),
            "error_rate_percent": round(failures / request_count * 100, 4),
            "graph_requests": int(graph["Request Count"]),
            "graph_p95_ms": float(graph["95%"]),
            "stats_csv": str(path),
            "html": str(args.raw_directory / f"locust-v2e-run-{number}.html"),
        }
        record["passed"] = (
            record["qps"] >= 200
            and record["p95_ms"] < 300
            and record["error_rate_percent"] < 0.1
        )
        runs.append(record)
    payload = {
        "workload": [
            "health",
            "task submit/status/result",
            "runtime thread GET",
            "runtime override POST",
            "Qdrant vector query",
            "Neo4j bounded graph query",
            "shared memory mutation",
        ],
        "runs": runs,
        "summary": {
            "minimum_qps": min(item["qps"] for item in runs),
            "maximum_p95_ms": max(item["p95_ms"] for item in runs),
            "maximum_graph_p95_ms": max(item["graph_p95_ms"] for item in runs),
            "maximum_error_rate_percent": max(item["error_rate_percent"] for item in runs),
            "passed": all(item["passed"] for item in runs),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False))
    if not payload["summary"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
