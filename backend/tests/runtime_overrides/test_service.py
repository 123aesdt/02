from datetime import timedelta

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from app.models.runtime_override import RuntimeOverride
from app.models.runtime_thread import RuntimeThread, RuntimeThreadEvent
from app.runtime_overrides.checkpoint_updater import LangGraphStateUpdater
from app.runtime_overrides.models import RuntimeOverrideRequest, RuntimeOverrideStatus
from app.runtime_overrides.policy import RuntimeOverridePolicy
from app.runtime_overrides.service import RuntimeOverrideService
from app.runtime_overrides.sqlalchemy_repository import SqlAlchemyRuntimeOverrideRepository
from app.runtime_threads.checkpoint_store import RedisRuntimeCheckpointStore
from app.runtime_threads.models import ThreadVersionConflict
from app.runtime_threads.sqlalchemy_repository import SqlAlchemyRuntimeThreadRepository
from app.security.permissions import Role
from tests.security_support import principal_for

from .factories import NOW
from .test_checkpoint_updater import graph_with_environment_boundary


class Lock:
    def __init__(self) -> None:
        self.acquired = False

    async def acquire(self, thread_id: str):
        self.acquired = True
        return type("Handle", (), {"acquired": True})()

    async def release(self, handle) -> bool:
        self.acquired = False
        return True


class EventPublisher:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.calls = 0

    async def publish_applied(self, item) -> None:
        self.calls += 1
        if self.fails:
            raise RuntimeError("transport contains redis://secret")


class SupervisorRuntimeOverrideService(RuntimeOverrideService):
    async def apply(self, thread_id, override_request, principal=None):
        return await super().apply(
            thread_id,
            override_request,
            principal or principal_for(Role.SUPERVISOR),
        )


def request(**changes: object) -> RuntimeOverrideRequest:
    values = {
        "idempotency_key": "override-key-1",
        "entity_type": "Vehicle",
        "entity_id": "vehicle-001",
        "field": "status",
        "old_value": "NORMAL",
        "new_value": "BROKEN",
        "reason": "vehicle telemetry confirms breakdown",
        "expected_version": 7,
        "expected_next_node": "capacity",
    }
    values.update(changes)
    return RuntimeOverrideRequest(**values)


async def service_fixture(sqlite_factory, *, event_fails: bool = False):
    saver = InMemorySaver()
    graph = graph_with_environment_boundary(saver)
    store = RedisRuntimeCheckpointStore(saver)
    config = {"configurable": {"thread_id": "thread-override", "checkpoint_ns": ""}}
    await graph.ainvoke({"vehicle_id": "vehicle-001", "vehicle_status": "NORMAL"}, config)
    snapshot = await graph.aget_state(config)
    checkpoint_id = snapshot.config["configurable"]["checkpoint_id"]
    with sqlite_factory() as session:
        session.add(
            RuntimeThread(
                thread_id="thread-override",
                task_id="TASK-override",
                status="STABLE",
                current_checkpoint_id=checkpoint_id,
                state_version=7,
                current_node="environment",
                next_node="capacity",
                checkpoint_count=4,
                resumed_count=0,
            )
        )
        session.commit()
    publisher = EventPublisher(fails=event_fails)
    service = SupervisorRuntimeOverrideService(
        SqlAlchemyRuntimeOverrideRepository(sqlite_factory),
        SqlAlchemyRuntimeThreadRepository(sqlite_factory),
        store,
        LangGraphStateUpdater(graph, store, max_checkpoint_bytes=1_048_576),
        RuntimeOverridePolicy(),
        Lock(),
        event_publisher=publisher,
        clock=lambda: NOW,
        intent_ttl=timedelta(seconds=30),
    )
    return service, store, publisher, checkpoint_id


@pytest.mark.asyncio
async def test_runtime_override_success(sqlite_factory) -> None:
    service, store, publisher, source_id = await service_fixture(sqlite_factory)

    result = await service.apply("thread-override", request())

    assert result.status is RuntimeOverrideStatus.APPLIED
    assert (result.before_state_version, result.after_state_version) == (7, 8)
    assert result.source_checkpoint_id == source_id
    assert result.result_checkpoint_id != source_id
    canonical = await store.get_exact("thread-override", result.result_checkpoint_id)
    assert canonical is not None and canonical.state["vehicle_status"] == "BROKEN"
    with sqlite_factory() as session:
        thread = session.scalar(select(RuntimeThread).where(RuntimeThread.thread_id == "thread-override"))
        assert thread is not None
        assert (thread.current_checkpoint_id, thread.state_version, thread.status, thread.checkpoint_count) == (
            result.result_checkpoint_id,
            8,
            "STABLE",
            4,
        )
    assert publisher.calls == 1


@pytest.mark.asyncio
async def test_runtime_override_idempotent_replay_does_not_update_again(sqlite_factory) -> None:
    service, _, publisher, _ = await service_fixture(sqlite_factory)
    first = await service.apply("thread-override", request())
    second = await service.apply("thread-override", request())

    assert second.status is RuntimeOverrideStatus.APPLIED
    assert second.result_checkpoint_id == first.result_checkpoint_id
    assert second.replayed is True
    assert publisher.calls == 1


@pytest.mark.asyncio
async def test_override_event_failure_does_not_reapply_state(sqlite_factory) -> None:
    service, _, publisher, _ = await service_fixture(sqlite_factory, event_fails=True)

    first = await service.apply("thread-override", request())
    second = await service.apply("thread-override", request())

    assert first.status is second.status is RuntimeOverrideStatus.APPLIED
    assert first.result_checkpoint_id == second.result_checkpoint_id
    assert first.after_state_version == second.after_state_version == 8
    assert first.event_status == "FAILED"
    assert publisher.calls == 1
    with sqlite_factory() as session:
        rows = list(session.scalars(select(RuntimeOverride)).all())
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_override_applied_implies_capacity_reads_new_value(sqlite_factory) -> None:
    service, store, _, _ = await service_fixture(sqlite_factory)
    applied = await service.apply("thread-override", request())

    record = await store.get_exact("thread-override", applied.result_checkpoint_id)

    assert applied.status is RuntimeOverrideStatus.APPLIED
    assert record is not None
    assert record.state["vehicle_status"] == "BROKEN"
    assert record.state["last_completed_node"] == "environment"


@pytest.mark.asyncio
async def test_runtime_override_state_version_increment(sqlite_factory) -> None:
    service, _, _, _ = await service_fixture(sqlite_factory)
    result = await service.apply("thread-override", request())
    assert (result.before_state_version, result.after_state_version) == (7, 8)


@pytest.mark.asyncio
async def test_runtime_override_next_node_reads_new_value(sqlite_factory) -> None:
    service, store, _, _ = await service_fixture(sqlite_factory)
    result = await service.apply("thread-override", request())
    record = await store.get_exact("thread-override", result.result_checkpoint_id)
    assert record is not None and record.state["vehicle_status"] == "BROKEN"


@pytest.mark.asyncio
async def test_runtime_override_expected_version_conflict(sqlite_factory) -> None:
    service, _, _, _ = await service_fixture(sqlite_factory)
    result = await service.apply("thread-override", request(expected_version=6))
    assert (result.status, result.error_code) == (
        RuntimeOverrideStatus.CONFLICT,
        "RUNTIME_STATE_VERSION_CONFLICT",
    )


@pytest.mark.asyncio
async def test_runtime_override_checkpoint_write_failure(sqlite_factory, monkeypatch) -> None:
    service, _, _, source_id = await service_fixture(sqlite_factory)

    async def fail(*args, **kwargs):
        raise ValueError("redis://credential-should-not-leak")

    monkeypatch.setattr(service._updater, "update", fail)
    result = await service.apply("thread-override", request())
    assert (result.status, result.error_code, result.error_summary) == (
        RuntimeOverrideStatus.FAILED,
        "CHECKPOINT_UPDATE_FAILED",
        "CHECKPOINT_UPDATE_FAILED",
    )
    with sqlite_factory() as session:
        thread = session.query(RuntimeThread).filter_by(thread_id="thread-override").one()
        assert (thread.status, thread.current_checkpoint_id, thread.state_version) == ("STABLE", source_id, 7)


@pytest.mark.asyncio
async def test_runtime_override_promotion_failure(sqlite_factory, monkeypatch) -> None:
    service, _, _, source_id = await service_fixture(sqlite_factory)

    def fail(*args, **kwargs):
        raise ThreadVersionConflict("mysql://credential-should-not-leak")

    monkeypatch.setattr(service._repository, "promote_applied", fail)
    result = await service.apply("thread-override", request())
    assert (result.status, result.error_code) == (
        RuntimeOverrideStatus.PARTIAL,
        "CHECKPOINT_PROMOTION_CONFLICT",
    )
    with sqlite_factory() as session:
        thread = session.query(RuntimeThread).filter_by(thread_id="thread-override").one()
        assert (thread.status, thread.current_checkpoint_id, thread.state_version) == ("OVERRIDING", source_id, 7)


@pytest.mark.asyncio
async def test_runtime_override_orphan_not_canonical(sqlite_factory, monkeypatch) -> None:
    service, store, _, source_id = await service_fixture(sqlite_factory)
    monkeypatch.setattr(
        service._repository,
        "promote_applied",
        lambda *args, **kwargs: (_ for _ in ()).throw(ThreadVersionConflict()),
    )
    result = await service.apply("thread-override", request())
    assert result.result_checkpoint_id is not None
    assert await store.get_exact("thread-override", result.result_checkpoint_id) is not None
    with sqlite_factory() as session:
        thread = session.query(RuntimeThread).filter_by(thread_id="thread-override").one()
        assert thread.current_checkpoint_id == source_id


@pytest.mark.asyncio
async def test_runtime_override_concurrent_race(sqlite_factory) -> None:
    import asyncio

    service, _, _, _ = await service_fixture(sqlite_factory)
    first, second = await asyncio.gather(
        service.apply("thread-override", request(idempotency_key="race-a", new_value="BROKEN")),
        service.apply("thread-override", request(idempotency_key="race-b", new_value="MAINTENANCE")),
    )
    assert sum(item.status is RuntimeOverrideStatus.APPLIED for item in (first, second)) == 1
    with sqlite_factory() as session:
        thread = session.query(RuntimeThread).filter_by(thread_id="thread-override").one()
        assert thread.state_version == 8


@pytest.mark.asyncio
async def test_runtime_override_audit(sqlite_factory) -> None:
    service, _, _, _ = await service_fixture(sqlite_factory)
    result = await service.apply("thread-override", request())
    with sqlite_factory() as session:
        event = session.query(RuntimeThreadEvent).filter_by(
            event_key=f"override:{result.override_id}:applied"
        ).one()
        assert event.metadata_json["operator_id"] == "test-supervisor"
        assert event.metadata_json["old_value"] == "NORMAL"
        assert event.metadata_json["new_value"] == "BROKEN"


@pytest.mark.asyncio
async def test_runtime_override_secret_safety(sqlite_factory, monkeypatch) -> None:
    service, _, _, _ = await service_fixture(sqlite_factory)

    async def fail(*args, **kwargs):
        raise ValueError("Authorization: Bearer secret; mysql://user:pass@host")

    monkeypatch.setattr(service._updater, "update", fail)
    result = await service.apply("thread-override", request())
    assert "secret" not in (result.error_summary or "").lower()
    assert "mysql://" not in (result.error_summary or "").lower()


@pytest.mark.asyncio
async def test_pending_ledger_crash_retries_without_duplicate_ledger(sqlite_factory, monkeypatch) -> None:
    service, _, _, _ = await service_fixture(sqlite_factory)

    async def crash(*args, **kwargs):
        raise RuntimeError("process stopped after PENDING")

    original = service._lock.acquire
    monkeypatch.setattr(service._lock, "acquire", crash)
    with pytest.raises(RuntimeError, match="process stopped"):
        await service.apply("thread-override", request())
    monkeypatch.setattr(service._lock, "acquire", original)

    result = await service.apply("thread-override", request())

    assert result.status is RuntimeOverrideStatus.APPLIED
    with sqlite_factory() as session:
        assert session.query(RuntimeOverride).count() == 1


@pytest.mark.asyncio
async def test_applying_crash_with_exact_result_requires_reconciliation(sqlite_factory, monkeypatch) -> None:
    service, _, _, _ = await service_fixture(sqlite_factory)

    class SimulatedProcessCrash(BaseException):
        pass

    def crash(*args, **kwargs):
        raise SimulatedProcessCrash

    original = service._repository.promote_applied
    monkeypatch.setattr(service._repository, "promote_applied", crash)
    with pytest.raises(SimulatedProcessCrash):
        await service.apply("thread-override", request())
    monkeypatch.setattr(service._repository, "promote_applied", original)

    result = await service.apply("thread-override", request())

    assert result.status is RuntimeOverrideStatus.PARTIAL
    assert result.result_checkpoint_id is not None
    assert result.error_code == "RUNTIME_OVERRIDE_RECONCILIATION_REQUIRED"
