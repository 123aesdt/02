"""Verify real Prometheus targets, CountyFlow metric metadata, and Grafana provisioning."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

TARGETS = ("backend", "worker-1", "worker-2")
REQUIRED_FAMILIES = (
    "countyflow_http_requests_total",
    "countyflow_agent_duration_seconds",
    "countyflow_vector_recall_total",
    "countyflow_graph_queries_total",
    "countyflow_checkpoint_operations_total",
    "countyflow_runtime_overrides_total",
    "countyflow_worker_messages_total",
    "countyflow_dependency_up",
)


def bearer_headers() -> dict[str, str]:
    token = os.environ.get("E2E_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("E2E_ACCESS_TOKEN is required for observability acceptance")
    return {"Authorization": f"Bearer {token}"}


def compose(*args: str) -> str:
    command = os.environ["DOCKER_COMMAND"]
    env_file = os.environ["COMPOSE_ENV_FILE"]
    result = subprocess.run([command, "compose", "--env-file", env_file, *args], capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Docker Compose command failed")
    return result.stdout


def prometheus(path: str) -> dict[str, object]:
    raw = compose("exec", "-T", "prometheus", "wget", "-qO-", f"http://localhost:9090{path}")
    payload = json.loads(raw)
    if payload.get("status") != "success":
        raise RuntimeError("Prometheus API returned a non-success status")
    return payload


def query_value(query: str) -> float:
    payload = prometheus("/api/v1/query?query=" + urllib.parse.quote(query))
    result = payload.get("data", {}).get("result", [])
    return sum(float(item["value"][1]) for item in result)


def mysql_scalar(query: str) -> int:
    command = f'MYSQL_PWD="$MYSQL_PASSWORD" mysql -N -u"$MYSQL_USER" -D"$MYSQL_DATABASE" -e "{query}"'
    raw = compose("exec", "-T", "mysql", "sh", "-c", command)
    values = [line.strip() for line in raw.splitlines() if line.strip().isdigit()]
    if len(values) != 1:
        raise RuntimeError("MySQL seed lookup failed")
    return int(values[0])


def api_json(path: str) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(f"http://localhost:8001{path}", headers=bearer_headers())
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.load(response)
        if not isinstance(payload, dict):
            raise TypeError("CountyFlow API returned a non-object payload")
        return response.status, payload


def submit_real_dispatch() -> str:
    order_id = mysql_scalar("SELECT id FROM orders WHERE order_no='ORDER-E2E-RAIN-001' LIMIT 1;")
    anomaly_id = mysql_scalar("SELECT id FROM anomalies WHERE anomaly_no='ANOM-E2E-RAIN-001' LIMIT 1;")
    request = urllib.request.Request(
        "http://localhost:8001/api/v1/dispatch-tasks",
        data=json.dumps(
            {
                "order_id": order_id,
                "anomaly_id": anomaly_id,
                "driver_id": "driver-li",
                "vehicle_id": "vehicle-001",
                "route_id": "xinping-road",
                "anomaly_type": "rain_slippery",
                "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
                "idempotency_key": f"v2g1-metrics-{uuid4().hex}",
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", **bearer_headers()},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        accepted = json.load(response)
        if response.status != 202 or not isinstance(accepted, dict):
            raise RuntimeError("Real dispatch was not accepted")
    task_id = str(accepted["task_id"])
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        _, status = api_json(f"/api/v1/dispatch-tasks/{task_id}")
        if status.get("ready") is True:
            _, result = api_json(f"/api/v1/dispatch-tasks/{task_id}/result")
            if result.get("audit", {}).get("result") != "APPROVED":
                raise RuntimeError("Real metrics dispatch did not preserve APPROVED audit")
            return task_id
        time.sleep(0.1)
    raise RuntimeError("Timed out waiting for real metrics dispatch")


def grafana(path: str) -> object:
    user = os.environ["GRAFANA_ADMIN_USER"]
    password = os.environ["GRAFANA_ADMIN_PASSWORD"]
    request = urllib.request.Request(f"http://localhost:{os.environ.get('GRAFANA_PORT', '3000')}{path}")
    request.add_header("Authorization", "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode())
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def run(output: Path) -> None:
    target_payload = prometheus("/api/v1/targets")
    active = target_payload["data"]["activeTargets"]
    targets = {
        str(item.get("labels", {}).get("job")): str(item.get("health"))
        for item in active
        if item.get("labels", {}).get("job") in TARGETS
    }
    if targets != {target: "up" for target in TARGETS}:
        raise RuntimeError(f"Prometheus targets are not all up: {targets}")

    scrape_text = "\n".join(
        compose("exec", "-T", "prometheus", "wget", "-qO-", f"http://{target}:9100/metrics") for target in TARGETS
    )
    missing = [family for family in REQUIRED_FAMILIES if f"# HELP {family} " not in scrape_text]
    if missing:
        raise RuntimeError(f"Required metric metadata is missing: {missing}")

    before_agents = query_value("countyflow_agent_executions_total")
    before_graph = query_value("countyflow_graph_queries_total")
    real_dispatch_task_id = submit_real_dispatch()
    deadline = time.monotonic() + 30
    agent_execution_delta = 0.0
    graph_query_delta = 0.0
    while time.monotonic() < deadline:
        agent_execution_delta = query_value("countyflow_agent_executions_total") - before_agents
        graph_query_delta = query_value("countyflow_graph_queries_total") - before_graph
        if agent_execution_delta >= 8 and graph_query_delta > 0:
            break
        time.sleep(1)
    if agent_execution_delta < 8 or graph_query_delta <= 0:
        raise RuntimeError("Real dispatch did not change bounded Agent and Graph metric families")

    health = grafana("/api/health")
    datasources = grafana("/api/datasources")
    dashboards = grafana("/api/search?query=CountyFlow")
    datasource_uids = [item.get("uid") for item in datasources if isinstance(item, dict)]
    dashboard_uids = [item.get("uid") for item in dashboards if isinstance(item, dict)]
    if health.get("database") != "ok" or "countyflow-prometheus" not in datasource_uids or "countyflow-v2-operations" not in dashboard_uids:
        raise RuntimeError("Grafana datasource or dashboard provisioning is incomplete")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "targets": targets,
                "required_metric_families": list(REQUIRED_FAMILIES),
                "real_dispatch_task_id": real_dispatch_task_id,
                "agent_execution_delta": agent_execution_delta,
                "graph_query_delta": graph_query_delta,
                "passed": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output.with_name("grafana-provisioning.json").write_text(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "health": "ok",
                "datasource_uid": "countyflow-prometheus",
                "dashboard_uid": "countyflow-v2-operations",
                "passed": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify backend, worker-1, worker-2, Prometheus, and Grafana observability integration")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
    print("Observability targets and Grafana provisioning verified.")


if __name__ == "__main__":
    main()
