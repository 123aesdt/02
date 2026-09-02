"""Summarize the authenticated V2-G2 Locust run without serializing credentials."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path


def _aggregated(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("Name") == "Aggregated":
                return row
    raise ValueError("Locust stats do not contain an Aggregated row")


def summarize(stats_path: Path, baseline_path: Path) -> dict[str, object]:
    row = _aggregated(stats_path)
    requests = int(row["Request Count"])
    failures = int(row["Failure Count"])
    qps = round(float(row["Requests/s"]), 3)
    p95_ms = float(row["95%"])
    error_rate = round((failures / requests * 100) if requests else 100.0, 4)
    baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_summary = baseline_payload["summary"]
    baseline_qps = float(baseline_summary["average_qps"])
    baseline_p95 = float(baseline_summary["maximum_p95_ms"])
    gates = {
        "qps_gte_200": qps >= 200,
        "p95_lt_300_ms": p95_ms < 300,
        "unexpected_error_rate_lt_0_1_percent": error_rate < 0.1,
    }
    return {
        "schema_version": 1,
        "benchmark": "v2-g2-authenticated-http",
        "timestamp": datetime.now(UTC).isoformat(),
        "security_on": {
            "profile": {
                "authentication": "development_jwt",
                "authorization": "bearer",
                "role": "DISPATCHER",
                "rate_limiting": "enabled",
                "principal_strategy": "unique_per_virtual_user",
                "users": 50,
                "duration_seconds": 60,
                "spawn_rate_per_second": 25,
            },
            "requests": requests,
            "failures": failures,
            "qps": qps,
            "p95_ms": p95_ms,
            "unexpected_error_rate_percent": error_rate,
            "stats_file": stats_path.as_posix(),
        },
        "security_off_baseline": {
            "evidence_kind": "historical_verified_pre_v2_g2",
            "source": baseline_path.as_posix(),
            "security_was_disabled_for_current_run": False,
            "average_qps": baseline_qps,
            "maximum_p95_ms": baseline_p95,
            "maximum_error_rate_percent": float(baseline_summary["maximum_error_rate_percent"]),
            "passed": bool(baseline_summary["passed"]),
        },
        "comparison": {
            "qps_delta_percent": round((qps - baseline_qps) / baseline_qps * 100, 3),
            "p95_delta_ms": round(p95_ms - baseline_p95, 3),
            "note": "OFF is the verified pre-V2-G2 historical baseline; the current runtime was never switched to anonymous mode.",
        },
        "gates": gates,
        "passed": all(gates.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.stats, args.baseline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = result["security_on"]
    print(
        "Security performance summary: "
        f"qps={summary['qps']}, p95_ms={summary['p95_ms']}, "
        f"unexpected_error_rate_percent={summary['unexpected_error_rate_percent']}, passed={result['passed']}"
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
