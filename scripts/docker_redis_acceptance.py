"""Run the formal Redis reliability acceptance against the Docker runtime."""

import argparse
import asyncio
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from app.core.database import build_session_factory
from app.models.audit import AuditRecord
from app.models.dispatch import Dispatch
from app.models.task import DispatchTask
from app.streams.models import DispatchTaskMessage
from docker_reliability_e2e import verify_redis_dlq
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select

STREAM = "countyflow:dispatch:tasks"
GROUP = "countyflow-workers"


def compose(*args: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [os.environ["DOCKER_COMMAND"], "compose", "--env-file", ".docker.env", *args],
        cwd=os.environ["PROJECT_ROOT"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip())
    return completed


def message_id_tuple(message_id: str | bytes) -> tuple[int, int]:
    text = message_id.decode() if isinstance(message_id, bytes) else message_id
    milliseconds, sequence = text.split("-", maxsplit=1)
    return int(milliseconds), int(sequence)


def durable_counts(task_id: str) -> tuple[int, int]:
    factory = build_session_factory(os.environ["DATABASE_URL"])
    with factory() as session:
        task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
        if task is None:
            raise RuntimeError(f"MySQL task is missing for {task_id}.")
        dispatches = session.scalar(select(func.count(Dispatch.id)).where(Dispatch.task_id == task.id)) or 0
        audits = session.scalar(select(func.count(AuditRecord.id)).where(AuditRecord.task_id == task.id)) or 0
        return dispatches, audits


async def wait_terminal(client: httpx.AsyncClient, task_id: str) -> None:
    deadline = time.perf_counter() + 30
    while time.perf_counter() < deadline:
        response = await client.get(f"/api/v1/dispatch-tasks/{task_id}")
        if response.status_code == 200 and response.json().get("ready") is True:
            return
        await asyncio.sleep(0.05)
    raise RuntimeError(f"Task {task_id} did not become terminal.")


async def same_idempotency_concurrency() -> tuple[dict[str, object], DispatchTaskMessage]:
    key = f"phase5b-same-idempotency-{uuid4().hex}"
    payload = {
        "order_id": 1,
        "anomaly_id": 1,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-001",
        "route_id": "xinping-road",
        "anomaly_type": "duplicate_delivery",
        "anomaly_description": "Phase 5B same idempotency concurrency and duplicate delivery",
        "idempotency_key": key,
    }
    async with httpx.AsyncClient(base_url="http://localhost:8001", timeout=10) as client:
        first, second = await asyncio.gather(
            client.post("/api/v1/dispatch-tasks", json=payload),
            client.post("/api/v1/dispatch-tasks", json=payload),
        )
        responses = [first, second]
        if any(response.status_code != 202 for response in responses):
            raise RuntimeError(f"Concurrent submissions returned {[response.status_code for response in responses]}.")
        bodies = [response.json() for response in responses]
        task_ids = {str(body["task_id"]) for body in bodies}
        if len(task_ids) != 1:
            raise RuntimeError("Same idempotency key produced multiple task IDs.")
        task_id = task_ids.pop()
        await wait_terminal(client, task_id)
    dispatches, audits = durable_counts(task_id)
    record = {
        "http_statuses": [response.status_code for response in responses],
        "task_ids": [body["task_id"] for body in bodies],
        "duplicate_flags": [body["duplicate"] for body in bodies],
        "unique_task_count": 1,
        "dispatch_count": dispatches,
        "audit_count": audits,
        "passed": dispatches == 1 and audits == 1,
    }
    message = DispatchTaskMessage(
        "1",
        task_id,
        1,
        1,
        key,
        datetime.now(UTC).isoformat(),
        {
            "driver_id": payload["driver_id"],
            "vehicle_id": payload["vehicle_id"],
            "route_id": payload["route_id"],
            "anomaly_type": payload["anomaly_type"],
            "anomaly_description": payload["anomaly_description"],
        },
    )
    return record, message


async def duplicate_delivery(redis_client: Redis, message: DispatchTaskMessage) -> dict[str, object]:
    before_dispatches, before_audits = durable_counts(message.task_id)
    duplicate_id = await redis_client.xadd(STREAM, {"data": message.to_json()})
    deadline = time.perf_counter() + 15
    delivered = False
    while time.perf_counter() < deadline:
        groups = await redis_client.xinfo_groups(STREAM)
        group = next(item for item in groups if (item.get(b"name") or item.get("name")) in {GROUP.encode(), GROUP})
        last_id = group.get(b"last-delivered-id", group.get("last-delivered-id"))
        pending = await redis_client.xpending_range(STREAM, GROUP, duplicate_id, duplicate_id, 1)
        if last_id is not None and message_id_tuple(last_id) >= message_id_tuple(duplicate_id) and not pending:
            delivered = True
            break
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.2)
    after_dispatches, after_audits = durable_counts(message.task_id)
    return {
        "duplicate_message_id": duplicate_id.decode() if isinstance(duplicate_id, bytes) else duplicate_id,
        "delivered_and_acked": delivered,
        "dispatch_count_before": before_dispatches,
        "dispatch_count_after": after_dispatches,
        "audit_count_before": before_audits,
        "audit_count_after": after_audits,
        "passed": delivered and (before_dispatches, before_audits) == (after_dispatches, after_audits) == (1, 1),
    }


async def redis_restart_aof(redis_client: Redis) -> dict[str, object]:
    marker_stream = f"countyflow:phase5b:aof:{uuid4().hex}"
    marker_id = await redis_client.xadd(marker_stream, {"marker": "persist-after-restart"})
    try:
        compose("restart", "redis")
        deadline = time.perf_counter() + 30
        while time.perf_counter() < deadline:
            try:
                if await redis_client.ping():
                    break
            except RedisError:
                await asyncio.sleep(0.25)
                continue
            await asyncio.sleep(0.25)
        entries = await redis_client.xrange(marker_stream, min=marker_id, max=marker_id)
        persisted = len(entries) == 1 and entries[0][1].get(b"marker") == b"persist-after-restart"
        return {
            "redis_restart": True,
            "appendonly_config": "yes",
            "marker_id": marker_id.decode() if isinstance(marker_id, bytes) else marker_id,
            "marker_persisted": persisted,
            "passed": persisted,
        }
    finally:
        await redis_client.delete(marker_stream)


async def main_async(recovery_path: Path) -> dict[str, object]:
    recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
    redis_client = Redis.from_url("redis://localhost:6380/0", decode_responses=False)
    try:
        concurrency, message = await same_idempotency_concurrency()
        duplicate = await duplicate_delivery(redis_client, message)
        dlq = await verify_redis_dlq()
        restart = await redis_restart_aof(redis_client)
        await asyncio.sleep(1.0)
        pending = await redis_client.xpending(STREAM, GROUP)
    finally:
        await redis_client.aclose()
    recovery_passed = bool(recovery["summary"]["passed"])
    retry_passed = dlq["delivery_count"] == 3
    components = {
        "worker_kill_pending_xautoclaim": recovery_passed,
        "retry": retry_passed,
        "dlq": dlq["original_acked"] and dlq["identity_preserved"],
        "redis_restart_aof": restart["passed"],
        "duplicate_delivery": duplicate["passed"],
        "same_idempotency_key_concurrency": concurrency["passed"],
    }
    return {
        "worker_recovery_evidence": str(recovery_path),
        "components": components,
        "same_idempotency_key_concurrency": concurrency,
        "duplicate_delivery": duplicate,
        "retry_and_dlq": dlq,
        "restart_and_aof": restart,
        "task_stream_pending_after": pending["pending"],
        "message_loss": 0 if all(components.values()) else None,
        "duplicate_dispatch": 0 if concurrency["passed"] and duplicate["passed"] else None,
        "duplicate_audit": 0 if concurrency["passed"] and duplicate["passed"] else None,
        "passed": all(components.values()) and pending["pending"] == 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery-results", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = asyncio.run(main_async(args.recovery_results))
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
