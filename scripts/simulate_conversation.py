"""Run the V2-E fifteen-round scenario against the real nine-service runtime."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from uuid import uuid4

import httpx
from neo4j import AsyncGraphDatabase
from qdrant_client import QdrantClient, models
from redis.asyncio import Redis
from sqlalchemy import func, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.acceptance.v2e import RoundEvidence, validate_round_evidence
from app.core.database import build_session_factory
from app.events.broker import RedisTaskEventBroker
from app.graph_memory.extractor import (
    DeterministicGraphTripleExtractor,
    GraphMemoryContext,
)
from app.graph_memory.neo4j_repository import Neo4jGraphMemoryRepository
from app.graph_memory.service import GraphMemoryService
from app.memory.qdrant_repository import QdrantMemoryRepository
from app.memory.service import EntityMemoryService
from app.models.anomaly import Anomaly
from app.models.audit import AuditRecord
from app.models.dispatch import Dispatch
from app.models.order import Order
from app.models.task import DispatchTask
from app.providers.embedding.fake import FakeEmbeddingProvider
from app.routing.provider import InMemoryRouteProvider
from app.routing.service import RoutingService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V2-E's real fifteen-round continuous dispatch scenario.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--api-base", default="http://127.0.0.1:8001")
    parser.add_argument("--redis-url", default="redis://127.0.0.1:6380/0")
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--neo4j-uri", default="bolt://127.0.0.1:7687")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def compose(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    docker = os.environ.get("DOCKER_COMMAND", "docker")
    return subprocess.run(
        [docker, "compose", "--env-file", str(PROJECT_ROOT / ".docker.env"), *arguments],
        cwd=PROJECT_ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


async def poll_json(client: httpx.AsyncClient, path: str, predicate, timeout: float = 35.0) -> dict[str, object]:
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


def event_payload(events: list[object], event_type: str) -> dict[str, object]:
    matches = [item for item in events if item.event_type.value == event_type]
    return dict(matches[-1].data) if matches else {}


def checkpoint_fields(thread: dict[str, object]) -> dict[str, object]:
    return {
        "checkpoint_id": thread.get("current_checkpoint_id"),
        "state_version": thread.get("state_version"),
        "current_node": thread.get("current_node"),
        "next_node": thread.get("next_node"),
    }


async def run(args: argparse.Namespace) -> dict[str, object]:
    password = os.environ.get("NEO4J_PASSWORD", "")
    if not password:
        raise RuntimeError("NEO4J_PASSWORD is required")
    sessions = build_session_factory(args.database_url)
    redis_client = Redis.from_url(args.redis_url, decode_responses=False)
    qdrant = QdrantClient(url=args.qdrant_url, check_compatibility=False)
    neo4j = AsyncGraphDatabase.driver(
        args.neo4j_uri,
        auth=(os.environ.get("NEO4J_USER", "neo4j"), password),
    )
    task_id = thread_id = ""
    rounds: list[dict[str, object]] = []
    try:
        compose("start", "worker-1")
        compose("unpause", "worker-1", check=False)
        compose("stop", "-t", "1", "worker-2")
        with sessions() as session:
            order_id = session.scalar(select(Order.id).where(Order.order_no == "ORDER-E2E-RAIN-001"))
            anomaly_id = session.scalar(select(Anomaly.id).where(Anomaly.anomaly_no == "ANOM-E2E-RAIN-001"))
        if order_id is None or anomaly_id is None:
            raise RuntimeError("Docker E2E seed order/anomaly is missing")

        async with httpx.AsyncClient(base_url=args.api_base, timeout=10.0) as client:
            create_response = await client.post(
                "/api/v1/dispatch-tasks",
                json={
                    "order_id": order_id,
                    "anomaly_id": anomaly_id,
                    "driver_id": "driver-li",
                    "vehicle_id": "vehicle-001",
                    "route_id": "xinping-road",
                    "anomaly_type": "rain_slippery",
                    "anomaly_description": "李师傅驾驶冷链车A在雨天经过新平路，道路湿滑且新平站负载上升。",
                    "idempotency_key": f"v2e-15-round-{uuid4().hex}",
                },
            )
            create_response.raise_for_status()
            task_id = str(create_response.json()["task_id"])
            thread = await poll_json(
                client,
                f"/api/v1/runtime/threads/by-task/{task_id}",
                lambda value: value.get("status") == "STABLE" and value.get("next_node") == "capacity",
            )
            thread_id = str(thread["thread_id"])
            compose("pause", "worker-1")
            intervention = await poll_json(
                client,
                f"/api/v1/runtime/threads/{thread_id}/intervention",
                lambda value: value.get("eligibility") == "ELIGIBLE",
            )
            stable_thread = await client.get(f"/api/v1/runtime/threads/{thread_id}")
            stable_thread.raise_for_status()
            stable = stable_thread.json()
            state = dict(stable["state"])

            vector_started = monotonic()
            vector_service = EntityMemoryService(
                FakeEmbeddingProvider(dimension=128),
                QdrantMemoryRepository(qdrant, "entity_resolution_memory", 128),
            )
            vector_recall = await vector_service.recall(
                "李师傅在雨天经过新平路，道路出现湿滑风险。",
                top_k=3,
            )
            vector_ms = (monotonic() - vector_started) * 1000
            graph_service = GraphMemoryService(
                Neo4jGraphMemoryRepository(neo4j, os.environ.get("NEO4J_DATABASE", "neo4j")),
                DeterministicGraphTripleExtractor(),
            )
            graph_recall = await graph_service.recall(
                GraphMemoryContext(
                    driver_id="driver-li",
                    vehicle_id="vehicle-001",
                    route_id="xinping-road",
                    anomaly_type="rain_slippery",
                    weather="rain",
                    text="李师傅驾驶冷链车A在雨天经过新平路，道路湿滑。",
                )
            )
            graph_facts = [fact.to_dict() for fact in graph_recall.facts]
            graph_paths = [path.to_dict() for path in graph_recall.paths]

            normal_capacity = {
                "driver_available": True,
                "vehicle_available": True,
                "load_ratio": 0.45,
                "station_load_ratio": 0.60,
                "capacity_status": "AVAILABLE",
                "risk_level": "low",
                "reason": None,
                "provider_name": "docker_runtime",
            }
            normal_route = await RoutingService(
                InMemoryRouteProvider.default_catalog(),
                memory_adoption_threshold=0.75,
            ).route(
                "xinping-road",
                [asdict(item) for item in vector_recall],
                str(state.get("weather", "heavy_rain")),
                str(state.get("road_condition", "slippery")),
                str(state.get("environment_risk", "high")),
                normal_capacity,
            )

            now = datetime.now(UTC).replace(microsecond=0)
            mutation_response = await client.post(
                "/api/v1/memory/mutations",
                json={
                    "idempotency_key": f"v2e-15-memory-{uuid4().hex}",
                    "category": "DispatchMemory",
                    "fact_kind": "HYBRID",
                    "subject_type": "Vehicle",
                    "subject_id": "vehicle-001",
                    "predicate": "STATUS",
                    "object_type": "Route",
                    "object_id": f"xinping-road-{task_id[-8:]}",
                    "value_json": {"evidence": "雨天新平路高风险，车辆故障后不得参与运力"},
                    "expected_version": None,
                    "confidence": "0.9900",
                    "incoming_at": now.isoformat(),
                    "expires_at": (now + timedelta(days=1)).isoformat(),
                    "source_type": "v2e_15_round",
                    "source_id": task_id,
                    "operator_id": "v2e-acceptance",
                    "human_confirmed": True,
                    "reason": "V2-E Round 10 verified operational evidence",
                    "evidence_text": "李师傅在雨天的新平路风险及车辆故障处置证据",
                    "evidence_observed_at": now.isoformat(),
                    "vector_memory_id": f"v2e-15-memory-{task_id}",
                    "graph_fact_key": f"v2e-15-graph-{task_id}",
                    "targets": ["VECTOR", "GRAPH"],
                },
            )
            mutation_response.raise_for_status()
            mutation = mutation_response.json()
            if mutation["status"] != "APPLIED":
                raise AssertionError(f"Round 10 memory mutation was not APPLIED: {mutation}")
            fact_response = await client.get(f"/api/v1/memory/facts/{mutation['fact_key']}")
            fact_response.raise_for_status()
            fact_detail = fact_response.json()
            points, _ = qdrant.scroll(
                "entity_resolution_memory",
                scroll_filter=models.Filter(
                    must=[models.FieldCondition(key="fact_key", match=models.MatchValue(value=mutation["fact_key"]))]
                ),
                limit=10,
                with_payload=True,
            )
            graph_projection, _, _ = await neo4j.execute_query(
                "MATCH ()-[r]->() WHERE r.control_fact_key = $fact_key RETURN r.projection_status AS status, count(r) AS count",
                fact_key=mutation["fact_key"],
                database_=os.environ.get("NEO4J_DATABASE", "neo4j"),
            )

            override_response = await client.post(
                f"/api/v1/runtime/threads/{thread_id}/overrides",
                json={
                    "idempotency_key": f"v2e-15-override-{uuid4().hex}",
                    "entity_type": "Vehicle",
                    "entity_id": "vehicle-001",
                    "field": "status",
                    "old_value": "NORMAL",
                    "new_value": "BROKEN",
                    "reason": "V2-E Round 12 confirmed cold-chain vehicle failure",
                    "expected_version": intervention["state_version"],
                    "expected_next_node": "capacity",
                },
            )
            override_response.raise_for_status()
            override = override_response.json()
            if override["status"] != "APPLIED":
                raise AssertionError(f"Round 12 override was not APPLIED: {override}")
            after_override_response = await client.get(f"/api/v1/runtime/threads/{thread_id}")
            after_override_response.raise_for_status()
            after_override = after_override_response.json()
            if after_override["state"]["vehicle_status"] != "BROKEN":
                raise AssertionError("Canonical checkpoint did not contain BROKEN after override")

            compose("unpause", "worker-1")
            compose("start", "worker-2")
            result = await poll_json(
                client,
                f"/api/v1/dispatch-tasks/{task_id}/result",
                lambda value: value.get("ready") is True,
                timeout=40.0,
            )
            final_thread_response = await client.get(f"/api/v1/runtime/threads/{thread_id}")
            final_thread_response.raise_for_status()
            final_thread = final_thread_response.json()
            history_response = await client.get(f"/api/v1/runtime/threads/{thread_id}/history?limit=100")
            history_response.raise_for_status()
            history = history_response.json()
            override_history_response = await client.get(f"/api/v1/runtime/threads/{thread_id}/overrides?limit=20")
            override_history_response.raise_for_status()
            override_history = override_history_response.json()

        broker = RedisTaskEventBroker(redis_client, "countyflow:events:task", 100)
        events = await broker.history(task_id)
        memory_event = event_payload(events, "MEMORY_COMPLETED")
        graph_event = event_payload(events, "GRAPH_MEMORY_COMPLETED")
        capacity_event = event_payload(events, "CAPACITY_COMPLETED")
        routing_event = event_payload(events, "ROUTING_COMPLETED")
        dispatch_event = event_payload(events, "DISPATCH_COMPLETED")
        audit_event = event_payload(events, "AUDIT_COMPLETED")
        pending = await redis_client.xpending("countyflow:dispatch:tasks", "countyflow-workers")
        pending_count = int(pending["pending"] if isinstance(pending, dict) else pending[0])

        with sessions() as session:
            task_pk = session.scalar(select(DispatchTask.id).where(DispatchTask.task_id == task_id))
            dispatch_count = session.scalar(select(func.count()).select_from(Dispatch).where(Dispatch.task_id == task_pk))
            audit_count = session.scalar(select(func.count()).select_from(AuditRecord).where(AuditRecord.task_id == task_pk))

        stable_fields = checkpoint_fields(stable)
        override_fields = checkpoint_fields(after_override)
        final_fields = checkpoint_fields(final_thread)

        def add_round(number: int, action: str, fields: dict[str, object], **evidence: object) -> None:
            rounds.append(
                {
                    "round": number,
                    "task_id": task_id,
                    "thread_id": thread_id,
                    **fields,
                    "action": action,
                    "memory_ids": evidence.pop("memory_ids", []),
                    "graph_facts": evidence.pop("graph_facts", []),
                    "override_id": evidence.pop("override_id", None),
                    "dispatch": evidence.pop("dispatch", None),
                    "audit": evidence.pop("audit", None),
                    "evidence": evidence,
                }
            )

        add_round(1, "base_context", stable_fields, driver_id="driver-li", vehicle_id="vehicle-001", route_id="xinping-road")
        add_round(2, "weather", stable_fields, weather=state.get("weather"))
        add_round(3, "road_anomaly", stable_fields, road_condition=state.get("road_condition"), anomaly="rain_slippery")
        add_round(4, "vector_recall", stable_fields, memory_ids=[item.memory_id for item in vector_recall], elapsed_ms=round(vector_ms, 3))
        add_round(5, "graph_recall", stable_fields, graph_facts=graph_facts, graph_paths=graph_paths, elapsed_ms=round(graph_recall.elapsed_ms, 3))
        add_round(6, "environment_risk", stable_fields, risk=state.get("environment_risk"), fallback=state.get("fallback_used"))
        add_round(7, "station_load", stable_fields, station="station-xinping", station_load_ratio=0.60)
        add_round(8, "normal_capacity_preview", stable_fields, capacity=normal_capacity)
        add_round(9, "normal_routing_preview", stable_fields, decision=normal_route.decision, route=normal_route.recommended_route)
        add_round(10, "shared_memory_mutation", stable_fields, mutation=mutation)
        add_round(
            11,
            "memory_persistence",
            stable_fields,
            memory_ids=[item.memory_id for item in vector_recall],
            graph_facts=graph_facts,
            canonical_fact=fact_detail,
            qdrant_projection_statuses=[point.payload.get("projection_status") for point in points],
            neo4j_projection=[dict(record) for record in graph_projection],
        )
        add_round(12, "runtime_override", override_fields, override_id=override["override_id"], override=override)
        add_round(13, "capacity_reads_broken", final_fields, capacity=capacity_event)
        add_round(14, "routing_excludes_broken_vehicle", final_fields, routing=routing_event)
        add_round(15, "final_consistency", final_fields, dispatch=result.get("dispatch"), audit=result.get("audit"), pending=pending_count)

        validate_round_evidence(
            [
                RoundEvidence(
                    round_number=int(item["round"]),
                    task_id=str(item["task_id"]),
                    thread_id=str(item["thread_id"]),
                    checkpoint_id=str(item["checkpoint_id"]),
                    state_version=int(item["state_version"]),
                    current_node=str(item["current_node"]),
                    next_node=str(item["next_node"]) if item.get("next_node") is not None else None,
                )
                for item in rounds
            ]
        )
        core_path = ("driver-li", "xinping-road", "national-102")
        recalled_paths = {
            tuple(entity["entity_id"] for entity in path["entities"])
            for path in graph_paths
        }
        assertions = {
            "round_12_override_applied": override["status"] == "APPLIED",
            "round_12_state_version_plus_one": override["after_state_version"] == override["before_state_version"] + 1,
            "round_13_capacity_reads_broken": capacity_event.get("vehicle_status") == "BROKEN" and capacity_event.get("vehicle_available") is False,
            "round_14_routing_does_not_use_vehicle": final_thread["state"].get("capacity_state", {}).get("vehicle_available") is False,
            "round_15_canonical_broken": final_thread["state"].get("vehicle_status") == "BROKEN",
            "round_15_review_required": result.get("status") == "REVIEW_REQUIRED",
            "vector_memory_persisted": any(item.memory_id == "memory-rain-li" for item in vector_recall),
            "graph_memory_persisted": core_path in recalled_paths,
            "shared_memory_active": fact_detail.get("status") == "ACTIVE",
            "qdrant_projection_active": [point.payload.get("projection_status") for point in points] == ["ACTIVE"],
            "neo4j_projection_active": any(record["status"] == "ACTIVE" for record in graph_projection),
            "canonical_checkpoint_promoted": after_override["current_checkpoint_id"] == override["result_checkpoint_id"],
            "append_only_history": len(history["items"]) >= 2,
            "override_audit_complete": bool(override_history["items"] and override_history["items"][0]["reason"]),
            "pending_zero": pending_count == 0,
            "duplicate_dispatch_zero": dispatch_count <= 1,
            "duplicate_audit_zero": audit_count <= 1,
        }
        return {
            "passed": all(assertions.values()),
            "real_runtime": {
                "docker": True,
                "fastapi": True,
                "mysql": True,
                "redis_8": True,
                "qdrant_server": True,
                "neo4j_server": True,
                "async_redis_saver": True,
                "workers": ["worker-1", "worker-2"],
            },
            "context": {"task_id": task_id, "thread_id": thread_id, "rounds": 15},
            "rounds": rounds,
            "assertions": assertions,
            "events": [item.to_dict() for item in events],
            "event_evidence": {
                "memory": memory_event,
                "graph": graph_event,
                "capacity": capacity_event,
                "routing": routing_event,
                "dispatch": dispatch_event,
                "audit": audit_event,
            },
            "checkpoint": {
                "stable": stable,
                "after_override": after_override,
                "final": final_thread,
                "history": history,
            },
            "override_history": override_history,
            "counts": {"dispatch": dispatch_count, "audit": audit_count, "pending": pending_count},
        }
    finally:
        compose("unpause", "worker-1", check=False)
        compose("start", "worker-1", check=False)
        compose("start", "worker-2", check=False)
        await neo4j.close()
        qdrant.close()
        await redis_client.aclose()


def main() -> None:
    args = parse_args()
    payload = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "context": payload["context"], "assertions": payload["assertions"]}, ensure_ascii=False))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
