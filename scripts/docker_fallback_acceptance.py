"""Run the formal HTTP-environment timeout fallback acceptance in Docker."""

import argparse
import asyncio
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import httpx
from app.acceptance.metrics import nearest_rank_percentile
from app.core.database import build_session_factory
from app.models.audit import AuditRecord
from app.models.dispatch import Dispatch
from app.models.task import DispatchTask
from redis.asyncio import Redis
from sqlalchemy import func, select

CONTAINER_NAME = "countyflow-phase5b-fallback-worker"
EVENT_PREFIX = "countyflow:events:task"


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


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run([os.environ["DOCKER_COMMAND"], *args], capture_output=True, text=True, check=False)
    if check and completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip())
    return completed


class SlowEnvironmentHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        time.sleep(2.0)
        body = json.dumps({"weather": "clear", "road_condition": "open", "risk_level": "low"}).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, _format: str, *_args: object) -> None:
        return


async def submit(client: httpx.AsyncClient, run: int) -> str:
    response = await client.post(
        "/api/v1/dispatch-tasks",
        json={
            "order_id": 1,
            "anomaly_id": 1,
            "driver_id": "driver-li",
            "vehicle_id": "vehicle-001",
            "route_id": "xinping-road",
            "anomaly_type": "environment_timeout",
            "anomaly_description": f"Phase 5B formal fallback run {run}",
            "idempotency_key": f"phase5b-fallback-{uuid4().hex}",
        },
    )
    if response.status_code != 202:
        raise RuntimeError(f"Fallback submission returned {response.status_code}: {response.text}")
    return str(response.json()["task_id"])


async def wait_for_result(client: httpx.AsyncClient, task_id: str) -> dict[str, object]:
    deadline = time.perf_counter() + 30
    while time.perf_counter() < deadline:
        response = await client.get(f"/api/v1/dispatch-tasks/{task_id}/result")
        if response.status_code == 200 and response.json().get("ready") is True:
            return response.json()
        await asyncio.sleep(0.05)
    raise RuntimeError(f"Fallback task {task_id} did not reach a terminal result.")


async def fallback_event(redis_client: Redis, task_id: str) -> dict[str, object]:
    entries = await redis_client.xrange(f"{EVENT_PREFIX}:{task_id}")
    for _entry_id, fields in entries:
        raw = fields.get(b"data", fields.get("data"))
        if isinstance(raw, bytes):
            raw = raw.decode()
        payload = json.loads(raw)
        if payload.get("event_type") == "ENVIRONMENT_FALLBACK":
            return payload
    raise RuntimeError(f"Fallback event is missing for {task_id}.")


def durable_counts(task_id: str) -> tuple[int, int]:
    factory = build_session_factory(os.environ["DATABASE_URL"])
    with factory() as session:
        task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
        if task is None:
            raise RuntimeError(f"MySQL task is missing for {task_id}.")
        dispatches = session.scalar(select(func.count(Dispatch.id)).where(Dispatch.task_id == task.id)) or 0
        audits = session.scalar(select(func.count(AuditRecord.id)).where(AuditRecord.task_id == task.id)) or 0
        return dispatches, audits


async def run(runs: int, port: int) -> dict[str, object]:
    server = ThreadingHTTPServer(("0.0.0.0", port), SlowEnvironmentHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    redis_client = Redis.from_url("redis://localhost:6380/0", decode_responses=False)
    docker("rm", "-f", CONTAINER_NAME, check=False)
    compose("stop", "worker-1", "worker-2")
    try:
        compose(
            "run",
            "--detach",
            "--name",
            CONTAINER_NAME,
            "--no-deps",
            "-e",
            "WORKER_CONSUMER_NAME=worker-fallback",
            "-e",
            "ENVIRONMENT_PROVIDER=http",
            "-e",
            f"ENVIRONMENT_API_BASE_URL=http://host.docker.internal:{port}",
            "-e",
            "ENVIRONMENT_API_TIMEOUT_SECONDS=0.8",
            "-e",
            "ENVIRONMENT_CB_FAILURE_THRESHOLD=100",
            "worker-1",
        )
        records: list[dict[str, object]] = []
        async with httpx.AsyncClient(base_url="http://localhost:8001", timeout=10) as client:
            for run_number in range(1, runs + 1):
                task_id = await submit(client, run_number)
                result = await wait_for_result(client, task_id)
                event = await fallback_event(redis_client, task_id)
                data = event["data"]
                elapsed_ms = float(data["environment_elapsed_ms"])
                dispatch_count, audit_count = durable_counts(task_id)
                dispatch = result.get("dispatch") or {}
                audit = result.get("audit") or {}
                record = {
                    "run": run_number,
                    "task_id": task_id,
                    "fallback_elapsed_ms": round(elapsed_ms, 3),
                    "fallback_reason": data.get("fallback_reason"),
                    "fallback_used": dispatch.get("fallback_used"),
                    "terminal_status": result.get("status"),
                    "audit_result": audit.get("result"),
                    "dispatch_count": dispatch_count,
                    "audit_count": audit_count,
                }
                record["passed"] = (
                    elapsed_ms <= 1000
                    and record["fallback_used"] is True
                    and record["fallback_reason"] == "Primary environment provider timed out."
                    and record["terminal_status"] in {"COMPLETED", "REVIEW_REQUIRED"}
                    and dispatch_count == 1
                    and audit_count == 1
                )
                records.append(record)
        elapsed = [float(record["fallback_elapsed_ms"]) for record in records]
        summary = {
            "minimum_ms": round(min(elapsed), 3),
            "average_ms": round(sum(elapsed) / len(elapsed), 3),
            "p95_ms": round(nearest_rank_percentile(elapsed, 95), 3),
            "maximum_ms": round(max(elapsed), 3),
            "passed": all(bool(record["passed"]) for record in records),
        }
        return {
            "metric_definition": "real Docker Worker primary HTTP timeout to static-route fallback",
            "primary_timeout_seconds": 0.8,
            "runs": records,
            "summary": summary,
        }
    finally:
        docker("rm", "-f", CONTAINER_NAME, check=False)
        compose("start", "worker-1", "worker-2", check=False)
        await redis_client.aclose()
        server.shutdown()
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.runs < 1:
        raise ValueError("--runs must be positive.")
    payload = asyncio.run(run(args.runs, args.port))
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if not payload["summary"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
