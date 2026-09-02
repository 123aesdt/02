"""Real Docker failure isolation for Neo4j, workers, Prometheus, and Grafana."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

API_BASE = "http://localhost:8001"


def bearer_headers() -> dict[str, str]:
    token = os.environ.get("E2E_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("E2E_ACCESS_TOKEN is required for observability failure acceptance")
    return {"Authorization": f"Bearer {token}"}


def compose(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        [os.environ["DOCKER_COMMAND"], "compose", "--env-file", os.environ["COMPOSE_ENV_FILE"], *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or "Docker Compose command failed")
    return result.stdout


def get_json(url: str) -> tuple[int, object | None]:
    request = urllib.request.Request(url, headers=bearer_headers() if url.startswith(API_BASE) else {})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)
    except (OSError, ValueError):
        return 0, None


def post_json(url: str, payload: dict[str, object]) -> tuple[int, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", **bearer_headers()},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.load(response)


def mysql_scalar(query: str) -> int:
    command = f'MYSQL_PWD="$MYSQL_PASSWORD" mysql -N -u"$MYSQL_USER" -D"$MYSQL_DATABASE" -e "{query}"'
    raw = compose("exec", "-T", "mysql", "sh", "-c", command)
    values = [line.strip() for line in raw.splitlines() if line.strip().isdigit()]
    if len(values) != 1:
        raise RuntimeError("MySQL seed lookup failed")
    return int(values[0])


def submit_and_wait(order_id: int, anomaly_id: int) -> str:
    status, accepted = post_json(
        "http://localhost:8001/api/v1/dispatch-tasks",
        {
            "order_id": order_id,
            "anomaly_id": anomaly_id,
            "driver_id": "driver-li",
            "vehicle_id": "vehicle-001",
            "route_id": "xinping-road",
            "anomaly_type": "rain_slippery",
            "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
            "idempotency_key": f"v2-g1-failure-{uuid4().hex}",
        },
    )
    if status != 202 or not isinstance(accepted, dict):
        raise RuntimeError("Business submission was not accepted")
    task_id = str(accepted["task_id"])
    wait_until(lambda: (payload := get_json(f"http://localhost:8001/api/v1/dispatch-tasks/{task_id}")[1]) is not None and payload.get("ready") is True)
    result_status, result = get_json(f"http://localhost:8001/api/v1/dispatch-tasks/{task_id}/result")
    if result_status != 200 or not isinstance(result, dict) or result.get("audit", {}).get("result") != "APPROVED":
        raise RuntimeError("Business dispatch did not complete with an approved audit")
    return task_id


def wait_until(check, *, timeout: float = 75) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(2)
    raise RuntimeError("Timed out waiting for failure-isolation invariant")


def target_health(job: str) -> str | None:
    raw = compose("exec", "-T", "prometheus", "wget", "-qO-", "http://localhost:9090/api/v1/targets", check=False)
    if not raw:
        return None
    for target in json.loads(raw).get("data", {}).get("activeTargets", []):
        if target.get("labels", {}).get("job") == job:
            return target.get("health")
    return None


def dependency_value(dependency: str) -> float | None:
    query = f'countyflow_dependency_up{{dependency="{dependency}"}}'
    url = "http://localhost:9090/api/v1/query?query=" + urllib.parse.quote(query)
    raw = compose("exec", "-T", "prometheus", "wget", "-qO-", url, check=False)
    if not raw:
        return None
    result = json.loads(raw).get("data", {}).get("result", [])
    return min(float(item["value"][1]) for item in result) if result else None


def run(output: Path) -> None:
    restored: list[str] = []
    checks: dict[str, bool] = {}
    task_ids: list[str] = []
    order_id = mysql_scalar("SELECT id FROM orders WHERE order_no='ORDER-E2E-RAIN-001' LIMIT 1;")
    anomaly_id = mysql_scalar("SELECT id FROM anomalies WHERE anomaly_no='ANOM-E2E-RAIN-001' LIMIT 1;")
    try:
        compose("stop", "neo4j")
        restored.append("neo4j")
        wait_until(lambda: dependency_value("neo4j") == 0)
        task_ids.append(submit_and_wait(order_id, anomaly_id))
        checks["neo4j_down_visible_and_business_continues"] = True
        compose("start", "neo4j")
        restored.remove("neo4j")
        wait_until(lambda: dependency_value("neo4j") == 1)

        compose("stop", "worker-1")
        restored.append("worker-1")
        wait_until(lambda: target_health("worker-1") == "down" and target_health("worker-2") == "up")
        task_ids.append(submit_and_wait(order_id, anomaly_id))
        checks["worker_isolation_and_worker_2_continues"] = True
        compose("start", "worker-1")
        restored.remove("worker-1")
        wait_until(lambda: target_health("worker-1") == "up")

        compose("stop", "prometheus")
        restored.append("prometheus")
        wait_until(lambda: get_json("http://localhost:8001/api/v1/observability/summary?window=5m")[0] == 503)
        task_ids.append(submit_and_wait(order_id, anomaly_id))
        checks["prometheus_unavailable_business_healthy"] = True
        compose("start", "prometheus")
        restored.remove("prometheus")
        wait_until(lambda: get_json("http://localhost:8001/api/v1/observability/summary?window=5m")[0] == 200)

        compose("stop", "grafana")
        restored.append("grafana")
        task_ids.append(submit_and_wait(order_id, anomaly_id))
        checks["grafana_isolated"] = get_json("http://localhost:8001/api/v1/observability/summary?window=5m")[0] == 200
        compose("start", "grafana")
        restored.remove("grafana")
        wait_until(lambda: get_json(f"http://localhost:{os.environ.get('GRAFANA_PORT', '3000')}/api/health")[0] == 200)
    finally:
        for service in reversed(restored):
            compose("start", service, check=False)

    if not checks or not all(checks.values()):
        raise RuntimeError(f"Failure isolation failed: {checks}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"timestamp": datetime.now(UTC).isoformat(), "checks": checks, "task_ids": task_ids, "passed": True}, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify neo4j, worker-1/worker-2, prometheus, and grafana failure isolation")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
    print("Observability failure isolation verified.")


if __name__ == "__main__":
    main()
