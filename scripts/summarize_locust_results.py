"""Summarize formal Locust CSV artifacts without changing their source data."""

import argparse
import csv
import json
from pathlib import Path


def aggregate_row(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return next(row for row in rows if row["Name"] == "Aggregated")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-directory", type=Path, default=Path("docs/verification/raw"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    records = []
    for run in range(1, 4):
        csv_path = args.raw_directory / f"locust-run-{run}_stats.csv"
        row = aggregate_row(csv_path)
        requests = int(row["Request Count"])
        failures = int(row["Failure Count"])
        record = {
            "run": run,
            "duration_seconds": 60,
            "users": 50,
            "requests": requests,
            "failures": failures,
            "qps": round(float(row["Requests/s"]), 3),
            "p50_ms": float(row["50%"]),
            "p95_ms": float(row["95%"]),
            "p99_ms": float(row["99%"]),
            "error_rate_percent": round(failures / requests * 100, 4),
            "stats_csv": str(csv_path),
            "html": str(args.raw_directory / f"locust-run-{run}.html"),
        }
        record["passed"] = record["qps"] >= 200 and record["p95_ms"] < 300 and record["error_rate_percent"] < 0.1
        records.append(record)
    payload = {
        "locust_version": "2.46.4",
        "runtime": [
            "Docker Backend",
            "MySQL 8.4",
            "Redis 8 AOF",
            "Qdrant Server",
            "Neo4j Community",
            "two Docker Workers",
        ],
        "configuration": {
            "users": 50,
            "spawn_rate_per_second": 25,
            "duration_seconds_per_formal_run": 60,
            "wait_time_seconds": "0.01-0.05",
            "task_weights": {"GET health": 50, "GET status": 30, "GET result": 19, "POST submission": 1},
            "post_strategy": "unique idempotency key per request",
            "graph_terminal_latency_in_http_metric": False,
        },
        "runs": records,
        "summary": {
            "minimum_qps": min(record["qps"] for record in records),
            "average_qps": round(sum(record["qps"] for record in records) / len(records), 3),
            "maximum_p95_ms": max(record["p95_ms"] for record in records),
            "maximum_error_rate_percent": max(record["error_rate_percent"] for record in records),
            "passed": all(record["passed"] for record in records),
        },
        "resource_sample": str(args.raw_directory / "locust-resource-sample.json"),
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if not payload["summary"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
