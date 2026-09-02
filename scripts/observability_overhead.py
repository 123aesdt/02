"""Compare real CountyFlow workloads with observability disabled and enabled."""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import math
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import websockets

API_BASE = "http://localhost:8001"


def bearer_headers() -> dict[str, str]:
    token = os.environ.get("E2E_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("E2E_ACCESS_TOKEN is required for observability overhead acceptance")
    return {"Authorization": f"Bearer {token}"}


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("A percentile requires at least one sample")
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * quantile) - 1)]


def compose(*args: str, metrics_enabled: bool | None = None, check: bool = True) -> str:
    environment = dict(os.environ)
    if metrics_enabled is not None:
        environment["METRICS_ENABLED"] = str(metrics_enabled).lower()
    result = subprocess.run(
        [os.environ["DOCKER_COMMAND"], "compose", "--env-file", os.environ["COMPOSE_ENV_FILE"], *args],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Docker Compose command failed")
    return result.stdout


def recreate(metrics_enabled: bool) -> None:
    compose(
        "up", "-d", "--force-recreate", "backend", "worker-1", "worker-2",
        metrics_enabled=metrics_enabled,
    )
    wait_until(lambda: get_json("/health")[0] == 200, timeout=90)


def get_json(path: str) -> tuple[int, dict[str, object] | None]:
    request = urllib.request.Request(f"{API_BASE}{path}", headers=bearer_headers())
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.load(response)
            return response.status, payload if isinstance(payload, dict) else None
    except urllib.error.HTTPError as error:
        try:
            payload = json.load(error)
        except (ValueError, OSError):
            payload = None
        return error.code, payload if isinstance(payload, dict) else None
    except (OSError, ValueError):
        return 0, None


def post_json(path: str, payload: dict[str, object]) -> tuple[int, dict[str, object] | None, float]:
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", **bearer_headers()},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = json.load(response)
            return response.status, body if isinstance(body, dict) else None, (time.perf_counter() - started) * 1000
    except urllib.error.HTTPError as error:
        try:
            body = json.load(error)
        except (ValueError, OSError):
            body = None
        return error.code, body if isinstance(body, dict) else None, (time.perf_counter() - started) * 1000


def wait_until(check, *, timeout: float = 45, interval: float = 0.05):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = check()
        if last:
            return last
        time.sleep(interval)
    raise RuntimeError(f"Timed out waiting for real workload state; last={last!r}")


def mysql_scalar(query: str) -> int:
    command = f'MYSQL_PWD="$MYSQL_PASSWORD" mysql -N -u"$MYSQL_USER" -D"$MYSQL_DATABASE" -e "{query}"'
    raw = compose("exec", "-T", "mysql", "sh", "-c", command)
    values = [line.strip() for line in raw.splitlines() if line.strip().isdigit()]
    if len(values) != 1:
        raise RuntimeError("MySQL seed lookup failed")
    return int(values[0])


def task_payload(order_id: int, anomaly_id: int, prefix: str) -> dict[str, object]:
    return {
        "order_id": order_id,
        "anomaly_id": anomaly_id,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-001",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "V2-G1 observability overhead workload",
        "idempotency_key": f"{prefix}-{uuid4().hex}",
    }


async def replay_events(task_id: str) -> list[dict[str, object]]:
    status, issued, _ = post_json("/api/v1/ws-tickets", {"target_type": "task", "target_id": task_id})
    if status != 201 or issued is None or not issued.get("ticket"):
        raise RuntimeError("Scoped WebSocket ticket issuance failed")
    ticket = urllib.parse.quote(str(issued["ticket"]), safe="")
    events: list[dict[str, object]] = []
    async with websockets.connect(
        f"ws://localhost:8001/api/v1/ws/tasks/{task_id}?ticket={ticket}",
        open_timeout=10,
    ) as socket:
        while True:
            event = json.loads(await asyncio.wait_for(socket.recv(), timeout=15))
            if isinstance(event, dict):
                events.append(event)
            if event.get("event_type") in {"TASK_COMPLETED", "TASK_REVIEW_REQUIRED", "TASK_FAILED"}:
                return events


def iso_seconds(value: object) -> float:
    if not isinstance(value, str):
        raise RuntimeError("Task event timestamp is missing")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def api_benchmark() -> tuple[float, float, float]:
    total = 3000

    def request() -> tuple[float, bool]:
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(f"{API_BASE}/health", timeout=5) as response:
                return (time.perf_counter() - started) * 1000, response.status == 200
        except OSError:
            return (time.perf_counter() - started) * 1000, False

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as executor:
        results = list(executor.map(lambda _: request(), range(total)))
    elapsed = time.perf_counter() - started
    latencies = [latency for latency, _ in results]
    errors = sum(not ok for _, ok in results)
    return percentile(latencies, 0.95), total / elapsed, errors / total


def ready_task(task_id: str):
    code, payload = get_json(f"/api/v1/dispatch-tasks/{task_id}")
    return payload if code == 200 and payload and payload.get("ready") is True else None


def graph_and_worker_benchmark(order_id: int, anomaly_id: int) -> tuple[float, float]:
    graph_durations: list[float] = []
    task_count = 3
    started = time.perf_counter()
    for _ in range(task_count):
        status, accepted, _ = post_json("/api/v1/dispatch-tasks", task_payload(order_id, anomaly_id, "v2g1-perf-graph"))
        if status != 202 or accepted is None:
            raise RuntimeError("Real graph workload submission failed")
        task_id = str(accepted["task_id"])
        wait_until(lambda: ready_task(task_id))
        events = asyncio.run(replay_events(task_id))
        started_event = next((item for item in events if item.get("event_type") == "GRAPH_MEMORY_STARTED"), None)
        completed_event = next((item for item in events if item.get("event_type") == "GRAPH_MEMORY_COMPLETED"), None)
        if started_event is None or completed_event is None:
            raise RuntimeError("Real graph workload did not emit bounded Graph Memory events")
        graph_durations.append((iso_seconds(completed_event.get("timestamp")) - iso_seconds(started_event.get("timestamp"))) * 1000)
    elapsed = time.perf_counter() - started
    return percentile(graph_durations, 0.95), task_count / elapsed


def eligible_thread(task_id: str):
    code, thread = get_json(f"/api/v1/runtime/threads/by-task/{task_id}")
    if code != 200 or not thread or thread.get("status") != "STABLE" or thread.get("next_node") != "capacity":
        return None
    context_code, context = get_json(f"/api/v1/runtime/threads/{thread['thread_id']}/intervention")
    return (thread, context) if context_code == 200 and context and context.get("eligibility") == "ELIGIBLE" else None


def override_benchmark(order_id: int, anomaly_id: int) -> float:
    latencies: list[float] = []
    compose("stop", "-t", "1", "worker-2")
    try:
        for _ in range(2):
            compose("start", "worker-1")
            compose("unpause", "worker-1", check=False)
            status, accepted, _ = post_json("/api/v1/dispatch-tasks", task_payload(order_id, anomaly_id, "v2g1-perf-override"))
            if status != 202 or accepted is None:
                raise RuntimeError("Real override workload submission failed")
            task_id = str(accepted["task_id"])
            thread, context = wait_until(lambda: eligible_thread(task_id))
            compose("pause", "worker-1")
            request = {
                "idempotency_key": f"v2g1-perf-override-{uuid4().hex}",
                "entity_type": "Vehicle", "entity_id": "vehicle-001", "field": "status",
                "old_value": "NORMAL", "new_value": "BROKEN",
                "reason": "V2-G1 observability overhead workload",
                "expected_version": context["state_version"], "expected_next_node": "capacity",
            }
            override_status, override, duration_ms = post_json(f"/api/v1/runtime/threads/{thread['thread_id']}/overrides", request)
            if override_status != 200 or not override or override.get("status") != "APPLIED":
                raise RuntimeError(f"Real override workload was not APPLIED: {override_status}")
            latencies.append(duration_ms)
            compose("unpause", "worker-1")
            wait_until(lambda: ready_task(task_id))
    finally:
        compose("unpause", "worker-1", check=False)
        compose("start", "worker-2", check=False)
    return percentile(latencies, 0.95)


def benchmark(order_id: int, anomaly_id: int) -> dict[str, float]:
    api_p95, qps, error_rate = api_benchmark()
    graph_p95, worker_throughput = graph_and_worker_benchmark(order_id, anomaly_id)
    override_p95 = override_benchmark(order_id, anomaly_id)
    return {
        "api_p95_ms": round(api_p95, 3), "graph_p95_ms": round(graph_p95, 3),
        "override_p95_ms": round(override_p95, 3), "worker_throughput": round(worker_throughput, 3),
        "qps": round(qps, 3), "error_rate": round(error_rate, 6),
    }


def run(output: Path) -> None:
    order_id = mysql_scalar("SELECT id FROM orders WHERE order_no='ORDER-E2E-RAIN-001' LIMIT 1;")
    anomaly_id = mysql_scalar("SELECT id FROM anomalies WHERE anomaly_no='ANOM-E2E-RAIN-001' LIMIT 1;")
    try:
        recreate(False)
        observability_off = benchmark(order_id, anomaly_id)
        recreate(True)
        observability_on = benchmark(order_id, anomaly_id)
    finally:
        compose("unpause", "worker-1", check=False)
        compose("start", "worker-1", "worker-2", check=False)
        recreate(True)
    passed = observability_on["qps"] >= 200 and observability_on["api_p95_ms"] < 300 and observability_on["error_rate"] < 0.001
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "workload": {"api_requests": 3000, "api_concurrency": 64, "graph_dispatches_per_mode": 3,
                     "runtime_overrides_per_mode": 2,
                     "real_services": ["backend", "worker-1", "worker-2", "mysql", "redis", "qdrant", "neo4j"]},
        "observability_off": observability_off,
        "observability_on": observability_on,
        "deltas_percent": {key: round((observability_on[key] - value) / value * 100, 3) if value else None
                           for key, value in observability_off.items()},
        "guardrails": {"minimum_qps": 200, "maximum_api_p95_ms": 300, "maximum_error_rate": 0.001},
        "passed": passed,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if not passed:
        raise RuntimeError(f"Observability performance guardrails failed: {observability_on}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare real observability-off/on CountyFlow workload overhead")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
    print("Observability overhead benchmark completed.")


if __name__ == "__main__":
    main()
