import logging
import os
import time
from uuid import uuid4

from app.acceptance.loadtest import build_dispatch_payload
from locust import HttpUser, between, events, task
from neo4j import GraphDatabase, Query
from qdrant_client import QdrantClient, models
from security_identity import development_bearer_identity

logging.getLogger("httpx").setLevel(logging.WARNING)

QDRANT = QdrantClient(os.getenv("QDRANT_URL", "http://localhost:6333"), check_compatibility=False)
NEO4J = GraphDatabase.driver(
    os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    auth=(os.getenv("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"]),
)
SEED_POINTS, _ = QDRANT.scroll("entity_resolution_memory", limit=1, with_vectors=True)
if not SEED_POINTS or SEED_POINTS[0].vector is None:
    raise RuntimeError("V2-E vector-memory seed is missing")
QUERY_VECTOR = SEED_POINTS[0].vector


def _record(request_type: str, name: str, started: float, *, error: Exception | None = None) -> None:
    events.request.fire(
        request_type=request_type,
        name=name,
        response_time=(time.perf_counter() - started) * 1000,
        response_length=0,
        exception=error,
        context={},
    )


class CountyFlowV2User(HttpUser):
    wait_time = between(0.01, 0.05)

    def on_start(self) -> None:
        self.task_id = os.environ["LOCUST_TASK_ID"]
        self.thread_id = os.environ["LOCUST_THREAD_ID"]
        identity = uuid4().hex
        principal = development_bearer_identity("SUPERVISOR", identity)
        self.client.headers.update(principal.headers)
        self.submit_token = f"v2e-{identity}"
        self.override_idempotency = f"v2e-load-terminal-{identity}"
        self.mutation_payload = {
            "idempotency_key": f"v2e-load-mutation-{identity}",
            "category": "DispatchMemory",
            "fact_kind": "ATTRIBUTE",
            "subject_type": "Vehicle",
            "subject_id": f"v2e-load-vehicle-{identity}",
            "predicate": "STATUS",
            "value_json": {"status": "NORMAL", "loadtest": True},
            "expected_version": None,
            "confidence": "0.9900",
            "incoming_at": "2026-08-27T00:00:00Z",
            "expires_at": "2026-08-28T00:00:00Z",
            "source_type": "v2e_loadtest",
            "source_id": f"v2e-load-{identity}",
            "human_confirmed": True,
            "reason": "V2-E isolated load-test memory mutation",
            "evidence_text": "V2-E isolated load-test evidence",
            "evidence_observed_at": "2026-08-27T00:00:00Z",
            "targets": ["GRAPH"],
        }

    @task(200)
    def health(self) -> None:
        self.client.get("/health", name="GET /health")

    @task(70)
    def task_status(self) -> None:
        self.client.get(f"/api/v1/dispatch-tasks/{self.task_id}", name="GET /api/v1/dispatch-tasks/:task_id")

    @task(30)
    def task_result(self) -> None:
        self.client.get(f"/api/v1/dispatch-tasks/{self.task_id}/result", name="GET /api/v1/dispatch-tasks/:task_id/result")

    @task(10)
    def runtime_thread(self) -> None:
        self.client.get(f"/api/v1/runtime/threads/{self.thread_id}", name="GET /api/v1/runtime/threads/:thread_id")

    @task(1)
    def runtime_override(self) -> None:
        with self.client.post(
            f"/api/v1/runtime/threads/{self.thread_id}/overrides",
            json={
                "idempotency_key": self.override_idempotency,
                "entity_type": "Vehicle",
                "entity_id": "vehicle-001",
                "field": "status",
                "old_value": "NORMAL",
                "new_value": "BROKEN",
                "reason": "V2-E terminal-thread load probe",
                "expected_version": 0,
                "expected_next_node": "capacity",
            },
            name="POST /api/v1/runtime/threads/:thread_id/overrides",
            catch_response=True,
        ) as response:
            payload = response.json()
            code = payload.get("code") or payload.get("error_code")
            safe_rejections = {
                "THREAD_TERMINAL",
                "RUNTIME_OVERRIDE_BUSY",
                "RUNTIME_STATE_VERSION_CONFLICT",
                "THREAD_NOT_STABLE",
            }
            if response.status_code == 409 and code in safe_rejections:
                response.success()
            else:
                response.failure(f"expected terminal 409, received {response.status_code}")

    @task(3)
    def vector_memory_query(self) -> None:
        started = time.perf_counter()
        error = None
        try:
            result = QDRANT.query_points(
                "entity_resolution_memory",
                query=QUERY_VECTOR,
                query_filter=models.Filter(
                    should=[
                        models.FieldCondition(key="projection_status", match=models.MatchValue(value="ACTIVE")),
                        models.IsEmptyCondition(is_empty=models.PayloadField(key="projection_status")),
                    ]
                ),
                limit=3,
            )
            if not result.points:
                raise AssertionError("vector memory query returned no points")
        except Exception as caught:  # noqa: BLE001 - every backend error must become a Locust failure.
            error = caught
        _record("MEMORY", "Qdrant vector query", started, error=error)

    @task(3)
    def graph_memory_query(self) -> None:
        started = time.perf_counter()
        error = None
        try:
            records, _, _ = NEO4J.execute_query(
                Query(
                    """
                    MATCH p=(start:GraphEntity {entity_key: $start_key})-[*1..3]-(related:GraphEntity)
                    WHERE all(r IN relationships(p) WHERE r.projection_status IS NULL OR r.projection_status = $active)
                    RETURN [n IN nodes(p) | n.entity_id] AS entity_ids
                    LIMIT $limit
                    """,
                    timeout=1.0,
                ),
                start_key="Driver:driver-li",
                active="ACTIVE",
                limit=10,
                database_=os.getenv("NEO4J_DATABASE", "neo4j"),
            )
            if not records:
                raise AssertionError("graph memory query returned no paths")
        except Exception as caught:  # noqa: BLE001 - every backend error must become a Locust failure.
            error = caught
        _record("GRAPH", "Neo4j bounded graph query", started, error=error)

    @task(1)
    def shared_memory_mutation(self) -> None:
        with self.client.post(
            "/api/v1/memory/mutations",
            json=self.mutation_payload,
            name="POST /api/v1/memory/mutations",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"expected 200, received {response.status_code}")

    @task(2)
    def submit(self) -> None:
        with self.client.post(
            "/api/v1/dispatch-tasks",
            json=build_dispatch_payload(self.submit_token),
            name="POST /api/v1/dispatch-tasks",
            catch_response=True,
        ) as response:
            if response.status_code != 202:
                response.failure(f"expected 202, received {response.status_code}")


@events.test_stop.add_listener
def close_store_clients(**_kwargs) -> None:
    QDRANT.close()
    NEO4J.close()
