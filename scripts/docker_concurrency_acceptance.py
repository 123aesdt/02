"""Run repeated real-MySQL optimistic-lock conflict acceptance trials."""

import argparse
import json
from pathlib import Path

from docker_reliability_e2e import verify_mysql_optimistic_lock


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.runs < 1:
        raise ValueError("--runs must be positive.")
    records = []
    for run_number in range(1, args.runs + 1):
        record = {"run": run_number, **verify_mysql_optimistic_lock()}
        record["passed"] = record["second_commit"] == "StaleDataError" and record["winner"] == "lock-session-a"
        records.append(record)
    intercepted = sum(bool(record["passed"]) for record in records)
    payload = {
        "metric_definition": "two real MySQL sessions read one SQLAlchemy version_id_col row; stale second commit must fail",
        "runs": records,
        "summary": {
            "runs": args.runs,
            "conflicts_intercepted": intercepted,
            "interception_rate": intercepted / args.runs,
            "silent_overwrites": args.runs - intercepted,
            "passed": intercepted == args.runs,
        },
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
