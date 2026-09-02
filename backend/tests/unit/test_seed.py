from types import SimpleNamespace

import pytest
from sqlalchemy import select

import app.seed as seed_module
from app.core.config import Settings
from app.models.anomaly import Anomaly
from app.models.audit import AuditRecord
from app.models.dispatch import Dispatch
from app.models.order import Order
from app.models.runtime_thread import RuntimeThread
from app.models.task import DispatchTask
from app.seed import seed_database
from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository


def test_development_seed_is_idempotent_and_diverse(sqlite_factory):
    seed_database(session_factory=sqlite_factory, runtime_profile="docker-dev")
    seed_database(session_factory=sqlite_factory, runtime_profile="docker-dev")

    with sqlite_factory() as session:
        orders = session.scalars(select(Order).where(Order.order_no.like("DEMO-ORDER-%"))).all()
        anomalies = session.scalars(select(Anomaly).where(Anomaly.anomaly_no.like("DEMO-ANOM-%"))).all()
        tasks = session.scalars(select(DispatchTask).where(DispatchTask.idempotency_key.like("demo-seed-%"))).all()
        dispatches = session.scalars(select(Dispatch).where(Dispatch.dispatch_no.like("DEMO-DISPATCH-%"))).all()
        audits = session.scalars(
            select(AuditRecord).join(DispatchTask).where(DispatchTask.idempotency_key.like("demo-seed-%"))
        ).all()
        threads = session.scalars(select(RuntimeThread).where(RuntimeThread.thread_id.like("demo-thread-%"))).all()

    assert len(orders) == 10
    assert len(anomalies) == 10
    assert {row.severity for row in anomalies} == {"HIGH", "MEDIUM", "LOW"}
    assert len(tasks) == 10
    assert sum(row.status == "REVIEW_REQUIRED" for row in tasks) == 4
    assert {row.assignee_subject_id for row in tasks} == {"CF-DEMO-001", "CF-DEMO-006"}
    assert sum(row.assignee_subject_id == "CF-DEMO-001" for row in tasks) == 5
    assert sum(row.assignee_subject_id == "CF-DEMO-006" for row in tasks) == 5
    assert {row.idempotency_key: row.assignee_subject_id for row in tasks} == {
        "demo-seed-001": "CF-DEMO-001",
        "demo-seed-002": "CF-DEMO-006",
        "demo-seed-003": "CF-DEMO-001",
        "demo-seed-004": "CF-DEMO-006",
        "demo-seed-005": "CF-DEMO-001",
        "demo-seed-006": "CF-DEMO-006",
        "demo-seed-007": "CF-DEMO-001",
        "demo-seed-008": "CF-DEMO-006",
        "demo-seed-009": "CF-DEMO-001",
        "demo-seed-010": "CF-DEMO-006",
    }
    assert len(dispatches) == 10
    assert len(audits) == 10
    assert len(threads) == 10
    assert {row.status for row in threads} == {"RUNNING", "STABLE", "OVERRIDING", "TERMINAL"}

    repository = SqlAlchemyWorkspaceReadRepository(sqlite_factory)
    assert repository.list_reviews(limit=20, before_id=None).provenance == "DEMO"
    assert repository.list_runtime_threads(limit=20, before_id=None, status=None).provenance == "DEMO"
    assert repository.count_domains().provenance == "DEMO"


def test_development_seed_backfills_assignment_without_resetting_existing_status(sqlite_factory):
    seed_database(session_factory=sqlite_factory, runtime_profile="docker-dev")
    with sqlite_factory() as session:
        task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == "DEMO-TASK-004"))
        assert task is not None
        task.status = "REJECTED"
        task.assignee_subject_id = None
        non_demo_task = DispatchTask(
            task_id="NON-DEMO-TASK-001",
            order_id=task.order_id,
            anomaly_id=task.anomaly_id,
            status="APPROVED",
            idempotency_key="non-demo-task-001",
            assignee_subject_id="CF-EXTERNAL-001",
        )
        session.add(non_demo_task)
        session.commit()

    seed_database(session_factory=sqlite_factory, runtime_profile="docker-dev")

    with sqlite_factory() as session:
        task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == "DEMO-TASK-004"))
        non_demo_task = session.scalar(
            select(DispatchTask).where(DispatchTask.task_id == "NON-DEMO-TASK-001")
        )
        assert task is not None
        assert non_demo_task is not None
        assert task.status == "REJECTED"
        assert task.assignee_subject_id == "CF-DEMO-006"
        assert non_demo_task.assignee_subject_id == "CF-EXTERNAL-001"


def test_production_seed_does_not_create_demo_business_rows(sqlite_factory):
    def forbidden_session_factory():
        raise AssertionError("production seed must not create a database session")

    seed_database(session_factory=forbidden_session_factory, runtime_profile="production")


def test_production_seed_entrypoint_constructs_no_external_dependencies(monkeypatch):
    def forbidden_dependency(*args, **kwargs):
        raise AssertionError("production seed must not construct external dependencies")

    monkeypatch.setattr(
        seed_module,
        "get_settings",
        lambda: SimpleNamespace(runtime_profile="production"),
    )
    monkeypatch.setattr(seed_module, "build_session_factory", forbidden_dependency)
    monkeypatch.setattr(seed_module, "QdrantClient", forbidden_dependency)
    monkeypatch.setattr(seed_module, "build_neo4j_driver", forbidden_dependency)
    monkeypatch.setattr(seed_module, "FakeEmbeddingProvider", forbidden_dependency)

    seed_module.main()


@pytest.mark.asyncio
async def test_production_memory_seed_constructs_no_qdrant_or_fake_provider(monkeypatch):
    def forbidden_dependency(*args, **kwargs):
        raise AssertionError("production memory seed must not construct dependencies")

    monkeypatch.setattr(
        seed_module,
        "get_settings",
        lambda: SimpleNamespace(runtime_profile="production"),
    )
    monkeypatch.setattr(seed_module, "QdrantClient", forbidden_dependency)
    monkeypatch.setattr(seed_module, "FakeEmbeddingProvider", forbidden_dependency)

    await seed_module.seed_memory()


@pytest.mark.asyncio
async def test_production_graph_seed_constructs_no_neo4j_driver(monkeypatch):
    def forbidden_dependency(*args, **kwargs):
        raise AssertionError("production graph seed must not construct dependencies")

    monkeypatch.setattr(
        seed_module,
        "get_settings",
        lambda: SimpleNamespace(runtime_profile="production"),
    )
    monkeypatch.setattr(seed_module, "build_neo4j_driver", forbidden_dependency)

    await seed_module.seed_graph()


@pytest.mark.asyncio
async def test_seed_memory_uses_the_configured_embedding_dimension(monkeypatch):
    captured: dict[str, int | str] = {}

    class RecordingClient:
        def close(self):
            captured["closed"] = "yes"

    class RecordingRepository:
        def __init__(self, client, collection_name, vector_dimension):
            captured["repository_dimension"] = vector_dimension

    class RecordingService:
        def __init__(self, provider, repository):
            captured["provider_dimension"] = provider.vector_dimension

        async def remember(self, record):
            captured["memory_id"] = record.memory_id
            captured["data_provenance"] = record.metadata["data_provenance"]

    settings = Settings(_env_file=None, embedding_dimension=16)
    monkeypatch.setattr(seed_module, "get_settings", lambda: settings)
    monkeypatch.setattr(seed_module, "QdrantClient", lambda url: RecordingClient())
    monkeypatch.setattr(seed_module, "QdrantMemoryRepository", RecordingRepository)
    monkeypatch.setattr(seed_module, "EntityMemoryService", RecordingService)

    await seed_module.seed_memory()

    assert captured == {
        "provider_dimension": 16,
        "repository_dimension": 16,
        "memory_id": "memory-rain-li",
        "data_provenance": "DEMO",
        "closed": "yes",
    }
