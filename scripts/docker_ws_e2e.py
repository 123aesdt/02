"""Exercise the Docker backend's real WebSocket event stream and replay path."""

import argparse
import asyncio
import json
import os
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

import websockets

WS_TICKET_PATH = "/api/v1/ws-tickets"


def access_token() -> str:
    token = os.getenv("E2E_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("E2E_ACCESS_TOKEN is required")
    return token


def post_task(order_id: int, anomaly_id: int, token: str) -> tuple[int, str]:
    payload = json.dumps(
        {
            "order_id": order_id,
            "anomaly_id": anomaly_id,
            "driver_id": "driver-li",
            "vehicle_id": "vehicle-001",
            "route_id": "xinping-road",
            "anomaly_type": "rain_slippery",
            "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
            "idempotency_key": f"docker-websocket-{uuid4().hex}",
        }
    ).encode()
    request = Request(
        "http://localhost:8001/api/v1/dispatch-tasks",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        body = json.loads(response.read())
        return response.status, str(body["task_id"])


def issue_ticket(task_id: str, token: str) -> str:
    request = Request(
        f"http://localhost:8001{WS_TICKET_PATH}",
        data=json.dumps({"target_type": "task", "target_id": task_id}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        if response.status != 201:
            raise RuntimeError("WebSocket ticket issuance failed")
        body = json.loads(response.read())
    ticket = body.get("ticket")
    if not isinstance(ticket, str) or not ticket:
        raise RuntimeError("WebSocket ticket response is invalid")
    return ticket


async def collect_events(task_id: str, token: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    ticket = issue_ticket(task_id, token)
    websocket_url = f"ws://localhost:8001/api/v1/ws/tasks/{task_id}?ticket={quote(ticket, safe='')}"
    async with websockets.connect(websocket_url, open_timeout=10) as socket:
        while True:
            event = json.loads(await asyncio.wait_for(socket.recv(), timeout=15))
            events.append(event)
            if event.get("event_type") in {"TASK_COMPLETED", "TASK_REVIEW_REQUIRED", "TASK_FAILED"}:
                break
    return events


async def verify(order_id: int, anomaly_id: int) -> None:
    token = access_token()
    status, task_id = post_task(order_id, anomaly_id, token)
    if status != 202:
        raise RuntimeError(f"Expected HTTP 202, got {status}.")
    events = await collect_events(task_id, token)
    event_types = {str(event.get("event_type")) for event in events}
    required = {
        "TASK_SNAPSHOT",
        "TASK_ACCEPTED",
        "WORKER_STARTED",
        "INTAKE_COMPLETED",
        "MEMORY_COMPLETED",
        "GRAPH_MEMORY_COMPLETED",
        "ENVIRONMENT_COMPLETED",
        "CAPACITY_COMPLETED",
        "ROUTING_COMPLETED",
        "DISPATCH_COMPLETED",
        "AUDIT_COMPLETED",
        "TASK_COMPLETED",
    }
    missing = required - event_types
    if missing:
        raise RuntimeError(f"WebSocket replay is missing events: {sorted(missing)}")

    graph_event = next(event for event in events if event.get("event_type") == "GRAPH_MEMORY_COMPLETED")
    graph_data = graph_event.get("data")
    if not isinstance(graph_data, dict) or graph_data.get("graph_memory_used") is not True:
        raise RuntimeError("Graph Memory was not used by the Docker E2E task.")
    facts = graph_data.get("graph_memory_facts")
    if not isinstance(facts, list):
        raise TypeError("Graph Memory facts are absent from the Docker E2E event.")
    fact_ids = {
        (
            str(fact.get("source", {}).get("entity_id")),
            str(fact.get("relation_type")),
            str(fact.get("target", {}).get("entity_id")),
        )
        for fact in facts
        if isinstance(fact, dict) and isinstance(fact.get("source"), dict) and isinstance(fact.get("target"), dict)
    }
    required_facts = {
        ("driver-li", "HAS_RISK_ON", "xinping-road"),
        ("xinping-road", "HIGH_RISK_WHEN", "rain"),
        ("national-102", "ALTERNATIVE_TO", "xinping-road"),
    }
    if not required_facts.issubset(fact_ids):
        raise RuntimeError(f"Docker Graph Memory evidence is incomplete: {sorted(required_facts - fact_ids)}")

    routing_event = next(event for event in events if event.get("event_type") == "ROUTING_COMPLETED")
    routing_data = routing_event.get("data")
    if not isinstance(routing_data, dict) or (
        routing_data.get("recommended_route"), routing_data.get("decision"), routing_data.get("memory_adopted")
    ) != ("national-102", "REROUTE", True):
        raise RuntimeError("Docker routing result regressed from the V1 core case.")
    print(f"[OK] WebSocket snapshot/replay, eight-agent events, and Graph Memory evidence verified for {task_id}.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--order-id", type=int, required=True)
    parser.add_argument("--anomaly-id", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(verify(args.order_id, args.anomaly_id))


if __name__ == "__main__":
    main()
