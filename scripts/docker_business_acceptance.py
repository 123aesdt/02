"""Validate the Phase 5B business acceptance workload and expected outcomes."""

import argparse
import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx


async def submit_and_wait(client: httpx.AsyncClient, *, manual: bool) -> dict[str, object]:
    token = uuid4().hex
    response = await client.post(
        "/api/v1/dispatch-tasks",
        json={
            "order_id": 1,
            "anomaly_id": 1,
            "driver_id": "driver-unavailable" if manual else "driver-li",
            "vehicle_id": "vehicle-unavailable" if manual else "vehicle-001",
            "route_id": "xinping-road",
            "anomaly_type": "capacity_unavailable" if manual else "rain_slippery",
            "anomaly_description": "Phase 5B manual review" if manual else "Phase 5B normal business acceptance",
            "idempotency_key": f"phase5b-business-{token}",
        },
    )
    if response.status_code != 202:
        raise RuntimeError(f"Business submission returned {response.status_code}: {response.text}")
    task_id = str(response.json()["task_id"])
    deadline = time.perf_counter() + 30
    while time.perf_counter() < deadline:
        status = await client.get(f"/api/v1/dispatch-tasks/{task_id}")
        if status.status_code == 200 and status.json().get("ready") is True:
            result = await client.get(f"/api/v1/dispatch-tasks/{task_id}/result")
            if result.status_code != 200:
                raise RuntimeError(f"Terminal task result returned {result.status_code}.")
            return {"status": status.json(), "result": result.json()}
        await asyncio.sleep(0.05)
    raise RuntimeError(f"Business task {task_id} did not become terminal.")


async def run(raw: Path) -> dict[str, object]:
    recovery = json.loads((raw / "worker-recovery-results.json").read_text(encoding="utf-8"))
    fallback = json.loads((raw / "fallback-results.json").read_text(encoding="utf-8"))
    concurrency = json.loads((raw / "concurrency-results.json").read_text(encoding="utf-8"))
    redis = json.loads((raw / "redis-reliability-results.json").read_text(encoding="utf-8"))
    async with httpx.AsyncClient(base_url="http://localhost:8001", timeout=10) as client:
        normal = await submit_and_wait(client, manual=False)
        manual = await submit_and_wait(client, manual=True)

    normal_passed = normal["status"]["status"] == "COMPLETED" and normal["result"]["audit"]["result"] == "APPROVED"
    manual_passed = (
        manual["status"]["status"] == "REVIEW_REQUIRED"
        and manual["status"]["requires_manual_review"] is True
        and manual["result"]["dispatch"] is None
        and manual["result"]["audit"] is None
    )
    scenarios = {
        "normal": normal_passed,
        "fallback": fallback["summary"]["passed"],
        "manual_review": manual_passed,
        "duplicate": redis["duplicate_delivery"]["passed"] and redis["same_idempotency_key_concurrency"]["passed"],
        "worker_recovery": recovery["summary"]["passed"],
        "concurrent_conflict": concurrency["summary"]["passed"],
    }
    unexpected = [name for name, passed in scenarios.items() if not passed]
    return {
        "scenarios": scenarios,
        "normal_task": normal,
        "manual_review_task": manual,
        "expected_outcomes": ["REVIEW_REQUIRED without automatic dispatch", "StaleDataError conflict"],
        "unexpected_business_errors": len(unexpected),
        "unexpected_scenarios": unexpected,
        "passed": not unexpected,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-directory", type=Path, default=Path("docs/verification/raw"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = asyncio.run(run(args.raw_directory))
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
