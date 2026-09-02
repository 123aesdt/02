"""Run three process-level worker crash/resume trials at a canonical checkpoint."""

import argparse
import asyncio
import json
import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx
from app.core.database import build_session_factory
from app.models.audit import AuditRecord
from app.models.dispatch import Dispatch
from app.models.runtime_thread import RuntimeThread, RuntimeThreadEvent
from app.models.shared_memory import MemoryMutation
from app.models.task import DispatchTask
from redis.asyncio import Redis
from sqlalchemy import func, select

STREAM = "countyflow:dispatch:tasks"
GROUP = "countyflow-workers"
CHECKPOINT_EVENT = "THREAD_CHECKPOINTED"
TARGET_NODE = "intake"


def authorization_headers() -> dict[str, str]:
    token = os.environ.get("E2E_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("E2E_ACCESS_TOKEN is required for authenticated checkpoint recovery")
    return {"Authorization": f"Bearer {token}"}


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [os.environ["DOCKER_COMMAND"], "compose", "--env-file", ".docker.env", *args],
        cwd=os.environ["PROJECT_ROOT"],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip())
    return completed


def docker(*args: str, check: bool = True) -> None:
    subprocess.run(
        [os.environ["DOCKER_COMMAND"], *args],
        check=check,
        capture_output=not check,
        text=not check,
    )


def container_id(service: str) -> str:
    value = compose("ps", "-q", service).stdout.strip()
    if not value:
        raise RuntimeError(f"{service} container is unavailable")
    return value


async def submit(run: int) -> str:
    async with httpx.AsyncClient(
        base_url="http://localhost:8001",
        timeout=10,
        headers=authorization_headers(),
    ) as client:
        response = await client.post(
            "/api/v1/dispatch-tasks",
            json={
                "order_id": 1,
                "anomaly_id": 1,
                "driver_id": "driver-li",
                "vehicle_id": "vehicle-001",
                "route_id": "xinping-road",
                "anomaly_type": "rain_slippery",
                "anomaly_description": f"V2-C checkpoint recovery run {run}",
                "idempotency_key": f"v2c-recovery-{uuid4().hex}",
            },
        )
        response.raise_for_status()
        return str(response.json()["task_id"])


async def wait_checkpoint(redis_client: Redis, task_id: str) -> dict[str, object]:
    event_stream = f"countyflow:events:task:{task_id}"
    cursor = "0-0"
    deadline = time.perf_counter() + 15
    while time.perf_counter() < deadline:
        batches = await redis_client.xread({event_stream: cursor}, count=20, block=1000)
        for _, entries in batches:
            for event_id, fields in entries:
                cursor = event_id.decode() if isinstance(event_id, bytes) else event_id
                raw = fields.get(b"data", fields.get("data"))
                payload = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                if payload.get("event_type") == CHECKPOINT_EVENT and payload.get("data", {}).get("node") == TARGET_NODE:
                    return payload
    raise RuntimeError("THREAD_CHECKPOINTED was not observed before timeout")


def durable_evidence(task_id: str, mutation_count_before: int, observed_checkpoint_id: str) -> dict[str, object]:
    factory = build_session_factory(os.environ["DATABASE_URL"])
    with factory() as session:
        task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
        thread = session.scalar(select(RuntimeThread).where(RuntimeThread.task_id == task_id))
        if task is None or thread is None:
            raise RuntimeError("Runtime task/thread metadata is missing")
        events = list(
            session.scalars(
                select(RuntimeThreadEvent)
                .where(RuntimeThreadEvent.thread_id == thread.thread_id)
                .order_by(RuntimeThreadEvent.id)
            )
        )
        resumed_events = [event for event in events if event.event_type == "THREAD_RESUMED"]
        promoted_events = [event for event in events if event.event_type == "CHECKPOINT_PROMOTED"]
        resumed_event = resumed_events[0] if len(resumed_events) == 1 else None
        post_resume = (
            [event for event in promoted_events if resumed_event is not None and event.id > resumed_event.id]
        )
        node_counts = {
            node: sum(event.node == node for event in promoted_events)
            for node in ("intake", "entity_memory", "graph_memory", "environment", "capacity", "routing", "dispatch", "audit")
        }
        dispatch = session.scalar(select(Dispatch).where(Dispatch.task_id == task.id))
        audit = session.scalar(select(AuditRecord).where(AuditRecord.task_id == task.id))
        mutation_count = session.scalar(select(func.count()).select_from(MemoryMutation)) or 0
        return {
            "thread_id": thread.thread_id,
            "canonical_checkpoint_id": thread.current_checkpoint_id,
            "state_version": thread.state_version,
            "resumed": sum(event.event_type == "THREAD_RESUMED" for event in events),
            "resumed_checkpoint_id": resumed_event.checkpoint_id if resumed_event else None,
            "resumed_next_node": resumed_event.next_node if resumed_event else None,
            "first_post_resume_node": post_resume[0].node if post_resume else None,
            "promoted_node_counts": node_counts,
            "resume_matches_observed_checkpoint": bool(
                resumed_event and resumed_event.checkpoint_id == observed_checkpoint_id
            ),
            "dispatch_count": session.scalar(select(func.count()).select_from(Dispatch).where(Dispatch.task_id == task.id)) or 0,
            "audit_count": session.scalar(select(func.count()).select_from(AuditRecord).where(AuditRecord.task_id == task.id)) or 0,
            "memory_mutation_count": mutation_count - mutation_count_before,
            "target_route": dispatch.target_route_id if dispatch else None,
            "decision": "REROUTE" if dispatch and dispatch.status == "REROUTED" else None,
            "audit": audit.result if audit else None,
            "memory": "memory-rain-li" if dispatch and "memory-rain-li" in (dispatch.decision_reason or "") else None,
            "status": task.status,
        }


async def wait_terminal(task_id: str) -> None:
    async with httpx.AsyncClient(
        base_url="http://localhost:8001",
        timeout=5,
        headers=authorization_headers(),
    ) as client:
        deadline = time.perf_counter() + 20
        while time.perf_counter() < deadline:
            response = await client.get(f"/api/v1/dispatch-tasks/{task_id}")
            if response.status_code == 200 and response.json().get("ready"):
                return
            await asyncio.sleep(0.05)
    raise RuntimeError("worker-2 did not reach terminal state")


async def wait_pending_zero(redis_client: Redis) -> dict[str, object]:
    deadline = time.perf_counter() + 1
    pending = await redis_client.xpending(STREAM, GROUP)
    while pending["pending"] != 0 and time.perf_counter() < deadline:
        await asyncio.sleep(0.02)
        pending = await redis_client.xpending(STREAM, GROUP)
    return pending


async def run_trial(redis_client: Redis, run: int) -> dict[str, object]:
    factory = build_session_factory(os.environ["DATABASE_URL"])
    with factory() as session:
        mutation_count_before = session.scalar(select(func.count()).select_from(MemoryMutation)) or 0
    compose("stop", "worker-1")
    docker("pause", container_id("worker-2"))
    os.environ["RUNTIME_CHECKPOINT_INTERRUPT_AFTER"] = TARGET_NODE
    try:
        compose("up", "-d", "--force-recreate", "worker-1")
    finally:
        os.environ.pop("RUNTIME_CHECKPOINT_INTERRUPT_AFTER", None)
    task_id = await submit(run)
    checkpoint = await wait_checkpoint(redis_client, task_id)
    docker("pause", container_id("worker-1"))
    killed_at = time.perf_counter()
    docker("kill", container_id("worker-1"))
    docker("unpause", container_id("worker-2"))
    await wait_terminal(task_id)
    pending = await wait_pending_zero(redis_client)
    recovery_seconds = time.perf_counter() - killed_at
    observed_checkpoint_id = str(checkpoint["data"]["checkpoint_id"])
    evidence = durable_evidence(task_id, mutation_count_before, observed_checkpoint_id)
    record = {
        "run": run,
        "worker_1": "worker-1",
        "worker_2": "worker-2",
        "checkpoint_node": TARGET_NODE,
        "observed_checkpoint_id": observed_checkpoint_id,
        "recovery_seconds": round(recovery_seconds, 3),
        "pending": pending["pending"],
        **evidence,
    }
    record["passed"] = (
        record["resumed"] == 1
        and record["resume_matches_observed_checkpoint"] is True
        and record["resumed_next_node"] == "entity_memory"
        and record["first_post_resume_node"] == "entity_memory"
        and all(count == 1 for count in record["promoted_node_counts"].values())
        and record["dispatch_count"] == 1
        and record["audit_count"] == 1
        and record["memory_mutation_count"] == 0
        and record["target_route"] == "national-102"
        and record["memory"] == "memory-rain-li"
        and record["decision"] == "REROUTE"
        and record["audit"] == "APPROVED"
        and record["pending"] == 0
        and recovery_seconds <= 5
    )
    return record


async def run(runs: int) -> dict[str, object]:
    redis_client = Redis.from_url("redis://127.0.0.1:6380/0", decode_responses=False)
    try:
        records = [await run_trial(redis_client, index) for index in range(1, runs + 1)]
    finally:
        os.environ.pop("RUNTIME_CHECKPOINT_INTERRUPT_AFTER", None)
        worker_2 = compose("ps", "-q", "worker-2", check=False).stdout.strip()
        if worker_2:
            docker("unpause", worker_2, check=False)
        compose("up", "-d", "--force-recreate", "worker-1", check=False)
        compose("start", "worker-2", check=False)
        await redis_client.aclose()
    return {"runs": records, "passed": len(records) >= 3 and all(record["passed"] for record in records)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Kill worker-1 after a canonical checkpoint and verify worker-2 resume.")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = asyncio.run(run(args.runs))
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
