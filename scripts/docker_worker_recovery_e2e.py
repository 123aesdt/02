"""Run auditable real Redis worker-kill recovery trials against Docker."""

import argparse
import asyncio
import json
import os
import re
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx
from app.acceptance.metrics import RecoveryRun, summarize_recovery
from app.core.database import build_session_factory
from app.models.audit import AuditRecord
from app.models.dispatch import Dispatch
from app.models.task import DispatchTask
from app.streams.models import DispatchTaskMessage
from redis.asyncio import Redis
from sqlalchemy import func, select

STREAM = "countyflow:dispatch:tasks"
GROUP = "countyflow-workers"
PENDING_MIN_IDLE_MS = 2_500
CLAIM_LOG = re.compile(r"recovery_scan_started_epoch_ms=(?P<scan>[0-9.]+) xautoclaim_elapsed_ms=(?P<claim>[0-9.]+)")


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [os.environ["DOCKER_COMMAND"], "compose", "--env-file", ".docker.env", *args],
        cwd=os.environ["PROJECT_ROOT"],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"docker compose {' '.join(args)} failed: {detail}")
    return completed


def docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([os.environ["DOCKER_COMMAND"], *args], capture_output=True, text=True, check=True)


def service_container_id(service: str) -> str:
    container_id = compose("ps", "-q", service).stdout.strip()
    if not container_id:
        raise RuntimeError(f"{service} container ID is unavailable.")
    return container_id


async def submit_probe(run: int) -> str:
    async with httpx.AsyncClient(base_url="http://localhost:8001", timeout=10) as client:
        response = await client.post(
            "/api/v1/dispatch-tasks",
            json={
                "order_id": 1,
                "anomaly_id": 1,
                "driver_id": "driver-li",
                "vehicle_id": "vehicle-001",
                "route_id": "xinping-road",
                "anomaly_type": "rain_slippery",
                "anomaly_description": f"Phase 5B worker recovery acceptance run {run}",
                "idempotency_key": f"phase5b-recovery-{uuid4().hex}",
            },
        )
        if response.status_code != 202:
            raise RuntimeError(f"Recovery probe submission returned HTTP {response.status_code}: {response.text}")
        return str(response.json()["task_id"])


async def pending_for(client: Redis, consumer: str | None = None) -> list[dict[str, object]]:
    return await client.xpending_range(STREAM, GROUP, "-", "+", 20, consumername=consumer)


async def wait_for_worker_one_pending(client: Redis, timeout_seconds: float = 10.0) -> dict[str, object]:
    deadline = time.perf_counter() + timeout_seconds
    while time.perf_counter() < deadline:
        pending = await pending_for(client, "worker-1")
        if pending:
            return pending[0]
        await asyncio.sleep(0.005)
    raise RuntimeError("No worker-1 pending message was observed before timeout.")


def message_id_text(pending: dict[str, object]) -> str:
    value = pending["message_id"]
    return value.decode() if isinstance(value, bytes) else str(value)


def pending_idle_ms(pending: dict[str, object]) -> int:
    value = pending.get("time_since_delivered", pending.get(b"time_since_delivered"))
    if not isinstance(value, int):
        raise TypeError("Redis pending idle time is unavailable.")
    return value


def consumer_text(pending: dict[str, object]) -> str:
    value = pending.get("consumer", pending.get(b"consumer"))
    return value.decode() if isinstance(value, bytes) else str(value)


async def message_task(client: Redis, message_id: str) -> DispatchTaskMessage:
    entries = await client.xrange(STREAM, min=message_id, max=message_id)
    if len(entries) != 1:
        raise RuntimeError("Killed worker message is missing from the task stream.")
    return DispatchTaskMessage.from_json(entries[0][1][b"data"])


async def observe_claim_and_ack(client: Redis, message_id: str, killed_at: float, timeout_seconds: float = 10.0) -> tuple[float, float]:
    claimed_at: float | None = None
    deadline = killed_at + timeout_seconds
    while time.perf_counter() < deadline:
        pending = await client.xpending_range(STREAM, GROUP, message_id, message_id, 1)
        now = time.perf_counter()
        if not pending:
            if claimed_at is None:
                raise RuntimeError("Recovered message was ACKed before worker-2 ownership could be observed.")
            return claimed_at, now
        if consumer_text(pending[0]) == "worker-2" and claimed_at is None:
            claimed_at = now
        await asyncio.sleep(0.01)
    raise RuntimeError("worker-2 did not ACK the killed message before timeout.")


def claim_log_timing(task_id: str) -> tuple[float, float]:
    logs = compose("logs", "--no-color", "worker-2").stdout.splitlines()
    for line in reversed(logs):
        if task_id not in line:
            continue
        matched = CLAIM_LOG.search(line)
        if matched:
            return float(matched.group("scan")), float(matched.group("claim"))
    raise RuntimeError(f"Recovery timing log is missing for {task_id}.")


def durable_counts(task_id: str) -> tuple[str, int, int]:
    factory = build_session_factory(os.environ["DATABASE_URL"])
    with factory() as session:
        task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
        if task is None:
            raise RuntimeError("Recovered DispatchTask is missing from MySQL.")
        dispatch_count = session.scalar(select(func.count(Dispatch.id)).where(Dispatch.task_id == task.id)) or 0
        audit_count = session.scalar(select(func.count(AuditRecord.id)).where(AuditRecord.task_id == task.id)) or 0
        return task.status, dispatch_count, audit_count


async def run_trial(client: Redis, run: int) -> dict[str, object]:
    compose("stop", "worker-1", "worker-2")
    compose("start", "worker-2")
    worker_two_id = service_container_id("worker-2")
    docker("pause", worker_two_id)
    worker_two_paused = True
    task_id = await submit_probe(run)
    factory = build_session_factory(os.environ["DATABASE_URL"])
    lock_session = factory()
    try:
        locked_task = lock_session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id).with_for_update())
        if locked_task is None:
            raise RuntimeError("Recovery probe task could not be row-locked.")
        compose("start", "worker-1")
        pending = await wait_for_worker_one_pending(client)
        message_id = message_id_text(pending)
        task = await message_task(client, message_id)
        if task.task_id != task_id:
            raise RuntimeError("Killed message is not the submitted recovery probe.")

        docker("unpause", worker_two_id)
        worker_two_paused = False
        before_kill = await client.xpending_range(STREAM, GROUP, message_id, message_id, 1)
        if not before_kill or consumer_text(before_kill[0]) != "worker-1":
            raise RuntimeError("worker-2 claimed the probe before worker-1 was killed.")
        idle_at_kill_ms = pending_idle_ms(before_kill[0])
        killed_at = time.perf_counter()
        killed_epoch_ms = time.time() * 1000
        docker("kill", service_container_id("worker-1"))
        lock_session.rollback()

        observed_claim_at, acked_at = await observe_claim_and_ack(client, message_id, killed_at)
        recovery_seconds = acked_at - killed_at
        eligibility_epoch_ms = killed_epoch_ms + max(0, PENDING_MIN_IDLE_MS - idle_at_kill_ms)
        scan_epoch_ms, xautoclaim_elapsed_ms = claim_log_timing(task_id)
        claim_epoch_ms = scan_epoch_ms + xautoclaim_elapsed_ms
        status, dispatch_count, audit_count = durable_counts(task_id)
        stream_entry_exists = bool(await client.xrange(STREAM, min=message_id, max=message_id))
        pending_after = len(await client.xpending_range(STREAM, GROUP, message_id, message_id, 1))
        message_lost = not stream_entry_exists or status not in {"APPROVED", "REVIEW_REQUIRED"}
        return {
            "run": run,
            "task_id": task_id,
            "message_id": message_id,
            "recovery_seconds": round(recovery_seconds, 3),
            "t1_to_t2_seconds": round(max(0.0, (eligibility_epoch_ms - killed_epoch_ms) / 1000), 3),
            "t2_to_t3_seconds": round(max(0.0, (scan_epoch_ms - eligibility_epoch_ms) / 1000), 3),
            "t3_to_t4_seconds": round(xautoclaim_elapsed_ms / 1000, 4),
            "t4_to_t6_seconds": round(max(0.0, (killed_epoch_ms + recovery_seconds * 1000 - claim_epoch_ms) / 1000), 3),
            "observed_claim_seconds": round(observed_claim_at - killed_at, 3),
            "pending_idle_ms_at_kill": idle_at_kill_ms,
            "dispatch_count": dispatch_count,
            "audit_count": audit_count,
            "pending": pending_after,
            "message_lost": message_lost,
            "terminal_status": status,
            "passed": recovery_seconds <= 5.0
            and dispatch_count == 1
            and audit_count == 1
            and pending_after == 0
            and not message_lost,
        }
    finally:
        lock_session.rollback()
        lock_session.close()
        if worker_two_paused:
            docker("unpause", worker_two_id)
        compose("start", "worker-1", check=False)
        compose("start", "worker-2", check=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.runs < 1:
        raise ValueError("--runs must be positive.")
    client = Redis.from_url("redis://localhost:6380/0", decode_responses=False)
    try:
        run_records = [await run_trial(client, run) for run in range(1, args.runs + 1)]
    finally:
        compose("start", "worker-1", check=False)
        compose("start", "worker-2", check=False)
        await client.aclose()

    runs = [
        RecoveryRun(
            int(record["run"]),
            float(record["recovery_seconds"]),
            int(record["dispatch_count"]),
            int(record["audit_count"]),
            int(record["pending"]),
            bool(record["message_lost"]),
        )
        for record in run_records
    ]
    summary = summarize_recovery(runs)
    payload = {
        "metric_definition": "worker-1 kill T1 to recovered message XACK T6 with worker-2 already running",
        "runs": run_records,
        "summary": {
            "minimum_seconds": round(summary.minimum_seconds, 3),
            "average_seconds": round(summary.average_seconds, 3),
            "p95_seconds": round(summary.p95_seconds, 3),
            "maximum_seconds": round(summary.maximum_seconds, 3),
            "failed_runs": summary.failed_runs,
            "passed": summary.passed,
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if not summary.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
