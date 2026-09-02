from datetime import timedelta

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.models.runtime_thread import RuntimeThread
from app.runtime_overrides.checkpoint_updater import LangGraphStateUpdater
from app.runtime_overrides.identity import payload_fingerprint
from app.runtime_overrides.models import RuntimeOverrideStatus
from app.runtime_overrides.reconciler import RuntimeOverrideReconciler
from app.runtime_overrides.sqlalchemy_repository import SqlAlchemyRuntimeOverrideRepository
from app.runtime_threads.checkpoint_store import RedisRuntimeCheckpointStore
from app.runtime_threads.sqlalchemy_repository import SqlAlchemyRuntimeThreadRepository

from .factories import NOW
from .test_checkpoint_updater import graph_with_environment_boundary
from .test_models import command


async def partial_override(sqlite_factory):
    saver = InMemorySaver()
    graph = graph_with_environment_boundary(saver)
    store = RedisRuntimeCheckpointStore(saver)
    config = {"configurable": {"thread_id": command().thread_id, "checkpoint_ns": ""}}
    await graph.ainvoke({"vehicle_id": "vehicle-001", "vehicle_status": "NORMAL"}, config)
    snapshot = await graph.aget_state(config)
    source_id = snapshot.config["configurable"]["checkpoint_id"]
    source = await store.get_exact(command().thread_id, source_id)
    assert source is not None
    with sqlite_factory() as session:
        session.add(
            RuntimeThread(
                thread_id=command().thread_id,
                task_id=command().thread_id.removeprefix("cf:dispatch:"),
                status="STABLE",
                current_checkpoint_id=source_id,
                state_version=7,
                current_node="environment",
                next_node="capacity",
                checkpoint_count=4,
                resumed_count=0,
            )
        )
        session.commit()
    threads = SqlAlchemyRuntimeThreadRepository(sqlite_factory)
    overrides = SqlAlchemyRuntimeOverrideRepository(sqlite_factory)
    item = command()
    overrides.begin_or_replay(item, payload_fingerprint(item), intent_expires_at=NOW + timedelta(seconds=30))
    threads.claim_override_boundary(
        item.thread_id,
        expected_checkpoint_id=source_id,
        expected_state_version=7,
        expected_next_node="capacity",
    )
    overrides.mark_applying(item.override_id, before_state_version=7, source_checkpoint_id=source_id, started_at=NOW)
    updated = await LangGraphStateUpdater(graph, store, max_checkpoint_bytes=1_048_576).update(
        source,
        {"vehicle_status": "BROKEN"},
        as_node="environment",
        expected_next_node="capacity",
        override_id=item.override_id,
    )
    overrides.attach_result_checkpoint(item.override_id, updated.record.checkpoint_id)
    overrides.mark_partial(item.override_id, error_code="CHECKPOINT_PROMOTION_CONFLICT", completed_at=NOW)
    return overrides, threads, store, item.override_id, source_id, updated.record.checkpoint_id


@pytest.mark.asyncio
async def test_runtime_override_reconciliation(sqlite_factory) -> None:
    overrides, threads, store, override_id, _, result_id = await partial_override(sqlite_factory)
    reconciler = RuntimeOverrideReconciler(overrides, threads, store, max_checkpoint_bytes=1_048_576)

    result = await reconciler.reconcile(override_id)

    assert result.status is RuntimeOverrideStatus.APPLIED
    assert result.result_checkpoint_id == result_id
    assert threads.get_by_thread_id(result.thread_id).current_checkpoint_id == result_id


@pytest.mark.asyncio
async def test_runtime_override_reconcile_conflict(sqlite_factory) -> None:
    overrides, threads, store, override_id, _, _ = await partial_override(sqlite_factory)
    with sqlite_factory() as session:
        row = session.query(RuntimeThread).filter_by(thread_id=command().thread_id).one()
        row.status = "STABLE"
        row.current_checkpoint_id = "checkpoint-c9"
        row.state_version = 8
        session.commit()
    reconciler = RuntimeOverrideReconciler(overrides, threads, store, max_checkpoint_bytes=1_048_576)

    result = await reconciler.reconcile(override_id)

    assert result.status is RuntimeOverrideStatus.CONFLICT
    assert result.error_code == "RUNTIME_STATE_VERSION_CONFLICT"
    assert threads.get_by_thread_id(result.thread_id).current_checkpoint_id == "checkpoint-c9"
