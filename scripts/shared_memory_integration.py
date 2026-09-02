import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from neo4j import AsyncGraphDatabase
from qdrant_client import QdrantClient
from redis.asyncio import Redis
from sqlalchemy import URL, create_engine, delete, func, select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import StaleDataError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.events.broker import InMemoryTaskEventBroker
from app.graph_memory.models import EntityType, GraphEntity, RelationType
from app.graph_memory.neo4j_repository import Neo4jGraphMemoryRepository
from app.graph_memory.schema import bootstrap_graph_schema
from app.memory.qdrant_repository import QdrantMemoryRepository
from app.models.shared_memory import (
    MemoryEvidence,
    MemoryMutation,
    MemoryMutationAttempt,
    SharedMemoryFact,
)
from app.providers.embedding.fake import FakeEmbeddingProvider
from app.shared_memory.events import MemoryMutationEventPublisher
from app.shared_memory.identity import build_fact_key, content_fingerprint
from app.shared_memory.models import (
    MemoryCategory,
    MemoryFactKind,
    MemoryTarget,
    SharedMemoryMutationCommand,
)
from app.shared_memory.neo4j_projection import Neo4jMemoryProjection
from app.shared_memory.policy import MemoryPolicySettings
from app.shared_memory.projection_builder import DefaultMemoryProjectionBuilder
from app.shared_memory.protocols import GraphProjection, VectorProjection
from app.shared_memory.qdrant_projection import QdrantMemoryProjection
from app.shared_memory.redis_lock import MemoryMutationLock
from app.shared_memory.service import SharedMemoryMutationService
from app.shared_memory.sqlalchemy_repository import SqlAlchemyMemoryControlRepository


class InjectedFinalizeCrash(BaseException):
    """Simulates process loss after the canonical MySQL commit."""


class FailOnceProjection:
    def __init__(self, delegate: object, *, operation: str, code: str) -> None:
        self._delegate = delegate
        self._operation = operation
        self._code = code
        self._failed = False

    async def stage(self, projection: object) -> None:
        if self._operation == "stage" and not self._failed:
            self._failed = True
            raise RuntimeError(self._code)
        await self._delegate.stage(projection)

    async def probe(self, mutation_id: str, control_version: int) -> str | None:
        return await self._delegate.probe(mutation_id, control_version)

    async def activate(self, projection: object) -> None:
        if self._operation == "activate" and not self._failed:
            self._failed = True
            raise InjectedFinalizeCrash()
        await self._delegate.activate(projection)

    async def retire_previous(self, projection: object) -> None:
        await self._delegate.retire_previous(projection)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate real MySQL, Redis, Qdrant, and Neo4j for V2-B."
    )
    parser.add_argument("--keep-artifacts", action="store_true")
    return parser.parse_args()


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def build_command(run_id: str, scenario: str) -> SharedMemoryMutationCommand:
    now = datetime.now(UTC)
    return SharedMemoryMutationCommand(
        idempotency_key=f"v2b-real-{run_id}-{scenario}",
        category=MemoryCategory.DISPATCH,
        fact_kind=MemoryFactKind.HYBRID,
        subject_type=EntityType.VEHICLE.value,
        subject_id=f"v2b-vehicle-{run_id}-{scenario}",
        predicate=RelationType.STATUS.value,
        object_type=EntityType.ROUTE.value,
        object_id=f"v2b-route-{run_id}-{scenario}",
        value_json={"resolution": "Broken"},
        expected_version=7,
        confidence=Decimal("0.9900"),
        incoming_at=now,
        expires_at=now + timedelta(days=1),
        source_type="v2b_real_integration",
        source_id=f"probe-{run_id}",
        operator_id="v2b-integration",
        human_confirmed=True,
        reason="verified replacement",
        evidence_text=f"new-v8-{scenario}",
        evidence_observed_at=now,
        vector_memory_id=f"v2b-memory-{run_id}-{scenario}",
        graph_fact_key=f"v2b-graph-{run_id}-{scenario}",
        targets=frozenset({MemoryTarget.VECTOR, MemoryTarget.GRAPH}),
    )


def old_vector(command: SharedMemoryMutationCommand, fact_key: str) -> VectorProjection:
    return VectorProjection(
        mutation_id=str(uuid4()),
        fact_key=fact_key,
        control_version=7,
        memory_id=command.vector_memory_id or fact_key,
        vector=tuple([1.0] + [0.0] * 127),
        driver_id=command.subject_id,
        route_id=command.object_id or "unknown-route",
        anomaly_type=command.predicate,
        resolution_text="Normal",
        metadata={"generation": "v7"},
        expires_at=command.expires_at,
    )


def old_graph(command: SharedMemoryMutationCommand, fact_key: str) -> GraphProjection:
    return GraphProjection(
        mutation_id=str(uuid4()),
        fact_key=fact_key,
        control_version=7,
        source=GraphEntity(EntityType.VEHICLE, command.subject_id, command.subject_id),
        relation_type=RelationType.STATUS,
        target=GraphEntity(EntityType.ROUTE, command.object_id or "unknown-route", command.object_id or "unknown-route"),
        confidence=Decimal("0.9000"),
        source_type="v2b_real_integration",
        evidence="old-v7",
        expires_at=command.expires_at,
        timestamp=datetime.now(UTC) - timedelta(minutes=5),
    )


class AcceptanceHarness:
    def __init__(self, run_id: str) -> None:
        mysql_url = URL.create(
            "mysql+pymysql",
            username=required("MYSQL_USER"),
            password=required("MYSQL_PASSWORD"),
            host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
            port=int(os.environ.get("MYSQL_PORT", "3306")),
            database=required("MYSQL_DATABASE"),
        )
        self.engine = create_engine(mysql_url, pool_pre_ping=True)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.repository = SqlAlchemyMemoryControlRepository(self.sessions)
        self.redis = Redis.from_url(os.environ.get("REDIS_URL", "redis://127.0.0.1:6380/0"))
        self.lock = MemoryMutationLock(self.redis, ttl_ms=10_000)
        self.collection = f"v2b_shared_memory_{run_id}"
        self.qdrant_client = QdrantClient(
            url=os.environ.get("QDRANT_URL", "http://127.0.0.1:6333"),
            check_compatibility=False,
        )
        self.vector = QdrantMemoryProjection(self.qdrant_client, self.collection, 128)
        self.vector_recall = QdrantMemoryRepository(self.qdrant_client, self.collection, 128)
        neo4j_password = required("NEO4J_PASSWORD")
        self.neo4j_database = os.environ.get("NEO4J_DATABASE", "neo4j")
        self.neo4j_driver = AsyncGraphDatabase.driver(
            os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687"),
            auth=(os.environ.get("NEO4J_USER", "neo4j"), neo4j_password),
        )
        self.graph = Neo4jMemoryProjection(
            self.neo4j_driver,
            self.neo4j_database,
            query_timeout_seconds=5.0,
        )
        self.graph_recall = Neo4jGraphMemoryRepository(
            self.neo4j_driver,
            self.neo4j_database,
            query_timeout_seconds=5.0,
        )
        self.builder = DefaultMemoryProjectionBuilder(FakeEmbeddingProvider(dimension=128))
        self.events = MemoryMutationEventPublisher(InMemoryTaskEventBroker())
        self.fact_keys: set[str] = set()
        self.subject_ids: set[str] = set()

    async def verify(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(select(func.count()).select_from(SharedMemoryFact)).scalar_one()
        if not await self.redis.ping():
            raise AssertionError("Redis did not answer PING")
        self.qdrant_client.get_collections()
        await self.neo4j_driver.verify_connectivity()
        await bootstrap_graph_schema(self.neo4j_driver, self.neo4j_database)

    def service(self, *, vector: object | None = None, graph: object | None = None) -> SharedMemoryMutationService:
        return SharedMemoryMutationService(
            repository=self.repository,
            lock=self.lock,
            policy_settings=MemoryPolicySettings(Decimal("0.8000"), Decimal("0.1000")),
            vector_projection=vector or self.vector,
            graph_projection=graph or self.graph,
            projection_builder=self.builder,
            event_publisher=self.events,
            clock=lambda: datetime.now(UTC),
            timeout_seconds=15.0,
        )

    async def seed_v7(self, command: SharedMemoryMutationCommand) -> tuple[str, tuple[float, ...]]:
        fact_key = build_fact_key(command)
        self.fact_keys.add(fact_key)
        self.subject_ids.add(command.subject_id)
        now = datetime.now(UTC) - timedelta(minutes=5)
        with self.sessions() as session:
            session.add(
                SharedMemoryFact(
                    fact_id=str(uuid4()),
                    fact_key=fact_key,
                    category=command.category.value,
                    fact_kind=command.fact_kind.value,
                    subject_type=command.subject_type,
                    subject_id=command.subject_id,
                    predicate=command.predicate,
                    object_type=command.object_type,
                    object_id=command.object_id,
                    value_json={"resolution": "Normal"},
                    content_fingerprint="0" * 64,
                    version=1,
                    confidence=Decimal("0.9000"),
                    status="ACTIVE",
                    expires_at=None,
                    vector_memory_id=command.vector_memory_id,
                    graph_fact_key=command.graph_fact_key,
                    last_mutation_id=str(uuid4()),
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
            session.execute(
                update(SharedMemoryFact)
                .where(SharedMemoryFact.fact_key == fact_key)
                .values(version=7, updated_at=now)
            )
            session.commit()
        vector = old_vector(command, fact_key)
        graph = old_graph(command, fact_key)
        await self.vector.stage(vector)
        await self.vector.activate(vector)
        await self.vector.retire_previous(vector)
        await self.graph.stage(graph)
        await self.graph.activate(graph)
        await self.graph.retire_previous(graph)
        return fact_key, vector.vector

    async def assert_v7_visible(
        self,
        command: SharedMemoryMutationCommand,
        fact_key: str,
        query: tuple[float, ...],
        *,
        canonical_version: int = 7,
    ) -> None:
        fact = self.repository.load_fact(fact_key)
        if fact is None or fact.version != canonical_version:
            raise AssertionError(
                f"Canonical fact version mismatch: expected={canonical_version}, actual={getattr(fact, 'version', None)}"
            )
        vectors = await self.vector_recall.search(list(query), top_k=10)
        resolutions = [item.historical_resolution for item in vectors if item.memory_id == command.vector_memory_id]
        if resolutions != ["Normal"]:
            raise AssertionError(f"STAGED Qdrant projection leaked: {resolutions}")
        relations = await self.graph_recall.find_related(
            [f"{EntityType.VEHICLE.value}:{command.subject_id}"], limit=10
        )
        visible = [(item.version, item.evidence) for item in relations if item.source.entity_id == command.subject_id]
        if visible != [(7, "old-v7")]:
            raise AssertionError(f"STAGED Neo4j projection leaked: {visible}")

    async def assert_v8_active(self, command: SharedMemoryMutationCommand, fact_key: str) -> None:
        fact = self.repository.load_fact(fact_key)
        if fact is None or fact.version != 8:
            raise AssertionError("Canonical fact did not reach v8")
        vector_spec = await self.builder.build_vector(command, "probe", fact_key, 8)
        vectors = await self.vector_recall.search(list(vector_spec.vector), top_k=10)
        resolutions = [item.historical_resolution for item in vectors if item.memory_id == command.vector_memory_id]
        if resolutions != ["Broken"]:
            raise AssertionError(f"Qdrant ACTIVE visibility is incorrect: {resolutions}")
        relations = await self.graph_recall.find_related(
            [f"{EntityType.VEHICLE.value}:{command.subject_id}"], limit=10
        )
        visible = [(item.version, item.evidence) for item in relations if item.source.entity_id == command.subject_id]
        if visible != [(8, command.evidence_text)]:
            raise AssertionError(f"Neo4j ACTIVE visibility is incorrect: {visible}")

        qdrant_statuses = await self._qdrant_statuses(fact_key)
        graph_statuses = await self._graph_statuses(fact_key)
        expected = {7: "RETIRED", 8: "ACTIVE"}
        if qdrant_statuses != expected or graph_statuses != expected:
            raise AssertionError(
                f"Projection retirement mismatch: qdrant={qdrant_statuses}, neo4j={graph_statuses}"
            )
        if await self.vector.count_points(command.vector_memory_id or fact_key, version=8) != 1:
            raise AssertionError("Qdrant v8 projection is duplicated")
        if await self.graph.count_edges(fact_key, version=8) != 1:
            raise AssertionError("Neo4j v8 projection is duplicated")

    async def assert_one_mutation_two_attempts(self, mutation_id: str) -> None:
        with self.sessions() as session:
            mutation_count = session.scalar(
                select(func.count()).select_from(MemoryMutation).where(MemoryMutation.mutation_id == mutation_id)
            )
            attempt_count = session.scalar(
                select(func.count())
                .select_from(MemoryMutationAttempt)
                .where(MemoryMutationAttempt.mutation_id == mutation_id)
            )
        if (mutation_count, attempt_count) != (1, 2):
            raise AssertionError(
                f"Expected one mutation and two attempts, got {(mutation_count, attempt_count)}"
            )

    async def _qdrant_statuses(self, fact_key: str) -> dict[int, str]:
        from qdrant_client import models

        points, _ = self.qdrant_client.scroll(
            self.collection,
            scroll_filter=models.Filter(
                must=[models.FieldCondition(key="fact_key", match=models.MatchValue(value=fact_key))]
            ),
            limit=20,
            with_payload=True,
        )
        return {int(point.payload["control_version"]): str(point.payload["projection_status"]) for point in points}

    async def _graph_statuses(self, fact_key: str) -> dict[int, str]:
        records, _, _ = await self.neo4j_driver.execute_query(
            """
            MATCH ()-[r]->()
            WHERE r.control_fact_key = $fact_key
            RETURN r.control_version AS version, r.projection_status AS status
            """,
            fact_key=fact_key,
            database_=self.neo4j_database,
        )
        return {int(record["version"]): str(record["status"]) for record in records}

    async def cleanup(self) -> None:
        if self.fact_keys:
            await self.neo4j_driver.execute_query(
                "MATCH ()-[r]->() WHERE r.control_fact_key IN $fact_keys DELETE r",
                fact_keys=sorted(self.fact_keys),
                database_=self.neo4j_database,
            )
        if self.subject_ids:
            await self.neo4j_driver.execute_query(
                "MATCH (n:GraphEntity) WHERE n.entity_id IN $entity_ids AND NOT (n)--() DELETE n",
                entity_ids=sorted(self.subject_ids),
                database_=self.neo4j_database,
            )
        if self.qdrant_client.collection_exists(self.collection):
            self.qdrant_client.delete_collection(self.collection)
        if self.fact_keys:
            with self.sessions() as session:
                mutation_ids = list(
                    session.scalars(
                        select(MemoryMutation.mutation_id).where(MemoryMutation.fact_key.in_(self.fact_keys))
                    ).all()
                )
                if mutation_ids:
                    session.execute(delete(MemoryMutationAttempt).where(MemoryMutationAttempt.mutation_id.in_(mutation_ids)))
                    session.execute(delete(MemoryEvidence).where(MemoryEvidence.mutation_id.in_(mutation_ids)))
                    session.execute(delete(MemoryMutation).where(MemoryMutation.mutation_id.in_(mutation_ids)))
                session.execute(delete(SharedMemoryFact).where(SharedMemoryFact.fact_key.in_(self.fact_keys)))
                session.commit()

    async def close(self) -> None:
        await self.neo4j_driver.close()
        await self.redis.aclose()
        self.qdrant_client.close()
        self.engine.dispose()


async def run_partial(
    harness: AcceptanceHarness,
    run_id: str,
    scenario: str,
    *,
    fail_target: MemoryTarget,
) -> str:
    command = build_command(run_id, scenario)
    fact_key, query = await harness.seed_v7(command)
    vector: object = harness.vector
    graph: object = harness.graph
    if fail_target is MemoryTarget.VECTOR:
        vector = FailOnceProjection(harness.vector, operation="stage", code="QDRANT_STAGE_FAILED")
    else:
        graph = FailOnceProjection(harness.graph, operation="stage", code="NEO4J_STAGE_FAILED")
    service = harness.service(vector=vector, graph=graph)

    partial = await service.mutate(command)
    if partial.status.value != "PARTIAL":
        raise AssertionError(f"Expected PARTIAL, got {partial.status.value}")
    await harness.assert_v7_visible(command, fact_key, query)
    applied = await service.resume_mutation(partial.mutation_id)
    if applied.status.value != "APPLIED":
        raise AssertionError(f"Expected APPLIED after resume, got {applied.status.value}")
    await harness.assert_v8_active(command, fact_key)
    await harness.assert_one_mutation_two_attempts(partial.mutation_id)
    return partial.mutation_id


async def run_finalize_crash(harness: AcceptanceHarness, run_id: str) -> str:
    command = build_command(run_id, "finalize-crash")
    fact_key, query = await harness.seed_v7(command)
    crashing_vector = FailOnceProjection(
        harness.vector,
        operation="activate",
        code="FINALIZE_CRASH",
    )
    service = harness.service(vector=crashing_vector)
    try:
        await service.mutate(command)
    except InjectedFinalizeCrash:
        pass
    else:
        raise AssertionError("Injected finalize crash did not escape the service boundary")

    stored = harness.repository.get_fact_detail(fact_key)["mutations"][0]
    if stored["status"] != "FINALIZING":
        raise AssertionError(f"Crash window was not FINALIZING: {stored['status']}")
    await harness.assert_v7_visible(command, fact_key, query, canonical_version=8)
    mutation_id = str(stored["mutation_id"])
    applied = await harness.service().resume_mutation(mutation_id)
    if applied.status.value != "APPLIED":
        raise AssertionError("FINALIZING mutation was not reconciled")
    await harness.assert_v8_active(command, fact_key)
    return mutation_id


async def run_redis_race(harness: AcceptanceHarness, run_id: str) -> int:
    key = f"smf_real_lock_{run_id}"
    first, second = await asyncio.gather(harness.lock.acquire(key), harness.lock.acquire(key))
    winners = [handle for handle in (first, second) if handle.acquired]
    if len(winners) != 1:
        raise AssertionError(f"Redis lock winners={len(winners)}")
    await harness.lock.release(winners[0])
    return len(winners)


def run_mysql_race(harness: AcceptanceHarness, run_id: str) -> int:
    command = build_command(run_id, "mysql-race")
    fact_key = build_fact_key(command)
    harness.fact_keys.add(fact_key)
    now = datetime.now(UTC)
    with harness.sessions() as session:
        session.add(
            SharedMemoryFact(
                fact_id=str(uuid4()),
                fact_key=fact_key,
                category=command.category.value,
                fact_kind=command.fact_kind.value,
                subject_type=command.subject_type,
                subject_id=command.subject_id,
                predicate=command.predicate,
                object_type=command.object_type,
                object_id=command.object_id,
                value_json={"resolution": "Normal"},
                content_fingerprint=content_fingerprint(command),
                version=1,
                confidence=Decimal("0.9000"),
                status="ACTIVE",
                vector_memory_id=command.vector_memory_id,
                graph_fact_key=command.graph_fact_key,
                last_mutation_id=str(uuid4()),
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
        session.execute(update(SharedMemoryFact).where(SharedMemoryFact.fact_key == fact_key).values(version=7))
        session.commit()

    session_a = harness.sessions()
    session_b = harness.sessions()
    winners = 0
    try:
        fact_a = session_a.scalar(select(SharedMemoryFact).where(SharedMemoryFact.fact_key == fact_key))
        fact_b = session_b.scalar(select(SharedMemoryFact).where(SharedMemoryFact.fact_key == fact_key))
        if fact_a is None or fact_b is None:
            raise AssertionError("MySQL race fact was not seeded")
        fact_a.confidence = Decimal("0.9100")
        session_a.commit()
        winners += 1
        fact_b.confidence = Decimal("0.9200")
        try:
            session_b.commit()
            winners += 1
        except StaleDataError:
            session_b.rollback()
    finally:
        session_a.close()
        session_b.close()
    with harness.sessions() as verify:
        version = verify.scalar(select(SharedMemoryFact.version).where(SharedMemoryFact.fact_key == fact_key))
    if winners != 1 or version != 8:
        raise AssertionError(f"MySQL optimistic race winners={winners}, version={version}")
    return winners


async def run_acceptance(*, keep_artifacts: bool = False) -> dict[str, object]:
    run_id = uuid4().hex[:10]
    harness = AcceptanceHarness(run_id)
    try:
        await harness.verify()
        first_mutation = await run_partial(
            harness,
            run_id,
            "qdrant-ok-neo4j-fail",
            fail_target=MemoryTarget.GRAPH,
        )
        second_mutation = await run_partial(
            harness,
            run_id,
            "neo4j-ok-qdrant-fail",
            fail_target=MemoryTarget.VECTOR,
        )
        crash_mutation = await run_finalize_crash(harness, run_id)
        redis_winners = await run_redis_race(harness, run_id)
        mysql_winners = run_mysql_race(harness, run_id)
        return {
            "real_services": ["mysql", "redis", "qdrant", "neo4j"],
            "qdrant_success_neo4j_failure": "PARTIAL_TO_APPLIED",
            "neo4j_success_qdrant_failure": "PARTIAL_TO_APPLIED",
            "staged_projection_invisible": True,
            "finalize_crash_reconciled": crash_mutation,
            "redis_single_lock_winner": redis_winners,
            "mysql_single_v7_to_v8_winner": mysql_winners,
            "one_mutation_two_attempts": [first_mutation, second_mutation],
            "projection_duplicates": 0,
        }
    finally:
        if not keep_artifacts:
            await harness.cleanup()
        await harness.close()


def main() -> None:
    args = parse_args()
    print(json.dumps(asyncio.run(run_acceptance(keep_artifacts=args.keep_artifacts)), sort_keys=True))


if __name__ == "__main__":
    main()
