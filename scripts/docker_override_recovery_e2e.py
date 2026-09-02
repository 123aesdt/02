"""Verify that a worker crash after APPLIED resumes from the override checkpoint."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from time import monotonic
from uuid import uuid4

import httpx
from redis.asyncio import Redis
from sqlalchemy import func, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.database import build_session_factory
from app.events.broker import RedisTaskEventBroker
from app.models.anomaly import Anomaly
from app.models.audit import AuditRecord
from app.models.dispatch import Dispatch
from app.models.order import Order
from app.models.task import DispatchTask


def command(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return command(os.environ["DOCKER_COMMAND"], "compose", "--env-file", ".docker.env", *args, check=check)


async def poll(client: httpx.AsyncClient, path: str, predicate, timeout: float = 35.0) -> dict[str, object]:
    deadline = monotonic() + timeout
    last: dict[str, object] = {}
    while monotonic() < deadline:
        response = await client.get(path)
        if response.status_code == 200:
            last = response.json()
            if predicate(last):
                return last
        await asyncio.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for {path}: {last}")


async def run_trial(
    run_number: int,
    sessions,
    redis_client: Redis,
    order_id: int,
    anomaly_id: int,
) -> dict[str, object]:
    compose("start", "worker-1")
    compose("unpause", "worker-1", check=False)
    compose("stop", "-t", "1", "worker-2")
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8001", timeout=10.0) as client:
        submitted = await client.post(
            "/api/v1/dispatch-tasks",
            json={
                "order_id": order_id,
                "anomaly_id": anomaly_id,
                "driver_id": "driver-li",
                "vehicle_id": "vehicle-001",
                "route_id": "xinping-road",
                "anomaly_type": "rain_slippery",
                "anomaly_description": f"V2-E override recovery run {run_number}",
                "idempotency_key": f"v2e-override-recovery-{uuid4().hex}",
            },
        )
        submitted.raise_for_status()
        task_id = str(submitted.json()["task_id"])
        thread = await poll(
            client,
            f"/api/v1/runtime/threads/by-task/{task_id}",
            lambda item: item.get("status") == "STABLE" and item.get("next_node") == "capacity",
        )
        compose("pause", "worker-1")
        thread_id = str(thread["thread_id"])
        intervention = await poll(
            client,
            f"/api/v1/runtime/threads/{thread_id}/intervention",
            lambda item: item.get("eligibility") == "ELIGIBLE",
        )
        override_response = await client.post(
            f"/api/v1/runtime/threads/{thread_id}/overrides",
            json={
                "idempotency_key": f"v2e-crash-override-{uuid4().hex}",
                "entity_type": "Vehicle",
                "entity_id": "vehicle-001",
                "field": "status",
                "old_value": "NORMAL",
                "new_value": "BROKEN",
                "reason": "V2-E worker crash after override acceptance",
                "expected_version": intervention["state_version"],
                "expected_next_node": "capacity",
            },
        )
        override_response.raise_for_status()
        override = override_response.json()
        canonical = await poll(
            client,
            f"/api/v1/runtime/threads/{thread_id}",
            lambda item: item.get("current_checkpoint_id") == override.get("result_checkpoint_id"),
        )
        worker_id = compose("ps", "-q", "worker-1").stdout.strip()
        killed_at = monotonic()
        command(os.environ["DOCKER_COMMAND"], "kill", worker_id)
        compose("start", "worker-2")
        result = await poll(
            client,
            f"/api/v1/dispatch-tasks/{task_id}/result",
            lambda item: item.get("ready") is True,
            timeout=40.0,
        )
        recovery_seconds = monotonic() - killed_at
        final_thread_response = await client.get(f"/api/v1/runtime/threads/{thread_id}")
        final_thread_response.raise_for_status()
        final_thread = final_thread_response.json()

    broker = RedisTaskEventBroker(redis_client, "countyflow:events:task", 100)
    events = await broker.history(task_id)
    capacity = [event for event in events if event.event_type.value == "CAPACITY_COMPLETED"][-1].data
    pending = await redis_client.xpending("countyflow:dispatch:tasks", "countyflow-workers")
    with sessions() as session:
        task_pk = session.scalar(select(DispatchTask.id).where(DispatchTask.task_id == task_id))
        dispatch_count = session.scalar(select(func.count()).select_from(Dispatch).where(Dispatch.task_id == task_pk))
        audit_count = session.scalar(select(func.count()).select_from(AuditRecord).where(AuditRecord.task_id == task_pk))
    record = {
        "run": run_number,
        "task_id": task_id,
        "thread_id": thread_id,
        "override_id": override["override_id"],
        "override_status": override["status"],
        "override_checkpoint_id": override["result_checkpoint_id"],
        "canonical_before_kill": canonical["current_checkpoint_id"],
        "canonical_after_resume": final_thread["current_checkpoint_id"],
        "final_vehicle_status": final_thread["state"].get("vehicle_status"),
        "capacity_vehicle_status": capacity.get("vehicle_status"),
        "capacity_vehicle_available": capacity.get("vehicle_available"),
        "terminal_status": result["status"],
        "dispatch_count": dispatch_count,
        "audit_count": audit_count,
        "pending": int(pending["pending"]),
        "recovery_seconds": round(recovery_seconds, 3),
    }
    record["passed"] = (
        record["override_status"] == "APPLIED"
        and record["canonical_before_kill"] == record["override_checkpoint_id"]
        and record["final_vehicle_status"] == "BROKEN"
        and record["capacity_vehicle_status"] == "BROKEN"
        and record["capacity_vehicle_available"] is False
        and record["terminal_status"] == "REVIEW_REQUIRED"
        and record["dispatch_count"] <= 1
        and record["audit_count"] <= 1
        and record["pending"] == 0
    )
    return record


async def run(runs: int, database_url: str) -> dict[str, object]:
    if runs < 5:
        raise ValueError("V2-E requires at least five override recovery trials")
    sessions = build_session_factory(database_url)
    redis_client = Redis.from_url("redis://127.0.0.1:6380/0", decode_responses=False)
    try:
        with sessions() as session:
            order_id = session.scalar(select(Order.id).where(Order.order_no == "ORDER-E2E-RAIN-001"))
            anomaly_id = session.scalar(select(Anomaly.id).where(Anomaly.anomaly_no == "ANOM-E2E-RAIN-001"))
        if order_id is None or anomaly_id is None:
            raise RuntimeError("Docker seed order/anomaly is missing")
        records = [
            await run_trial(index, sessions, redis_client, order_id, anomaly_id)
            for index in range(1, runs + 1)
        ]
        return {"passed": all(record["passed"] for record in records), "runs": records}
    finally:
        compose("unpause", "worker-1", check=False)
        compose("start", "worker-1", check=False)
        compose("start", "worker-2", check=False)
        await redis_client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run(args.runs, args.database_url))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
