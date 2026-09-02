from dataclasses import replace
from datetime import UTC, datetime
from typing import NotRequired, TypedDict

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.runtime_threads.checkpoint_store import RedisRuntimeCheckpointStore
from app.runtime_threads.models import CheckpointRecord, RuntimeThreadSnapshot, RuntimeThreadStatus, ThreadVersionConflict
from app.runtime_threads.reconciler import ThreadCheckpointReconciler
from app.runtime_threads.runner import CheckpointedGraphRunner, RuntimeThreadCheckpointError


class _State(TypedDict):
    value: int
    last_completed_node: NotRequired[str]
    completed_node_count: NotRequired[int]


def _thread() -> RuntimeThreadSnapshot:
    now = datetime.now(UTC)
    return RuntimeThreadSnapshot(
        thread_id="cf:dispatch:TASK-0123456789abcdef0123456789abcde",
        task_id="TASK-0123456789abcdef0123456789abcde",
        status=RuntimeThreadStatus.RUNNING,
        current_checkpoint_id=None,
        state_version=0,
        current_node=None,
        next_node="node_a",
        checkpoint_count=0,
        checkpoint_size_bytes=None,
        last_event_sequence=None,
        worker_consumer=None,
        resumed_count=0,
        created_at=now,
        updated_at=now,
        terminal_at=None,
        row_version=1,
    )


class _FailingRepository:
    def __init__(self):
        self.commands = []

    def promote_checkpoint(self, command):
        self.commands.append(command)
        raise ThreadVersionConflict("simulated CAS loss")


def _graph(saver, counters):
    async def node_a(state: _State):
        counters["node_a"] += 1
        return {"value": state["value"] + 1, "last_completed_node": "node_a", "completed_node_count": 1}

    async def node_b(state: _State):
        counters["node_b"] += 1
        return {"value": state["value"] + 1, "last_completed_node": "node_b", "completed_node_count": 2}

    graph = StateGraph(_State)
    graph.add_node("node_a", node_a)
    graph.add_node("node_b", node_b)
    graph.add_edge(START, "node_a")
    graph.add_edge("node_a", "node_b")
    graph.add_edge("node_b", END)
    return graph.compile(checkpointer=saver)


@pytest.mark.asyncio
async def test_checkpoint_registry_partial_failure():
    saver = InMemorySaver()
    store = RedisRuntimeCheckpointStore(saver)
    repository = _FailingRepository()
    counters = {"node_a": 0, "node_b": 0}
    published_events: list[object] = []
    runner = CheckpointedGraphRunner(
        _graph(saver, counters),
        repository,
        store,
        node_order=("node_a", "node_b"),
        max_checkpoint_bytes=1_048_576,
        worker_consumer="worker-1",
        event_publisher=published_events.append,
    )

    with pytest.raises(RuntimeThreadCheckpointError, match="CHECKPOINT_PROMOTION_CONFLICT"):
        await runner.run_new(_thread(), {"value": 0})

    redis_records = await store.list_bounded(_thread().thread_id, 10)
    assert any(record.state.get("last_completed_node") == "node_a" for record in redis_records)
    assert repository.commands[0].expected_checkpoint_id is None
    assert counters == {"node_a": 1, "node_b": 0}
    assert published_events == []


def _record(
    checkpoint_id: str,
    *,
    parent_id: str | None,
    node: str,
    count: int,
    size: int = 512,
) -> CheckpointRecord:
    return CheckpointRecord(
        thread_id=_thread().thread_id,
        checkpoint_id=checkpoint_id,
        parent_checkpoint_id=parent_id,
        checkpoint_namespace="",
        state={"last_completed_node": node, "completed_node_count": count},
        metadata={"source": "loop"},
        config={"configurable": {"thread_id": _thread().thread_id, "checkpoint_id": checkpoint_id}},
        serialized_size_bytes=size,
    )


class _RecordStore:
    def __init__(self, records):
        self.records = records
        self.limits = []

    async def list_bounded(self, thread_id, limit):
        self.limits.append(limit)
        return self.records[:limit]


class _PromotingRepository:
    def __init__(self, thread):
        self.thread = thread
        self.commands = []

    def promote_checkpoint(self, command):
        if self.thread.current_checkpoint_id == command.checkpoint_id:
            return self.thread
        self.commands.append(command)
        self.thread = replace(
            self.thread,
            status=RuntimeThreadStatus.STABLE,
            current_checkpoint_id=command.checkpoint_id,
            state_version=self.thread.state_version + 1,
            checkpoint_count=self.thread.checkpoint_count + 1,
            current_node=command.node,
            next_node=command.next_node,
            checkpoint_size_bytes=command.checkpoint_size_bytes,
        )
        return self.thread


def _canonical_a() -> RuntimeThreadSnapshot:
    return replace(
        _thread(),
        status=RuntimeThreadStatus.STABLE,
        current_checkpoint_id="checkpoint-a",
        state_version=1,
        checkpoint_count=1,
        current_node="node_a",
        next_node="node_b",
        checkpoint_size_bytes=512,
    )


@pytest.mark.asyncio
async def test_checkpoint_reconciliation():
    thread = _canonical_a()
    store = _RecordStore([_record("checkpoint-b", parent_id="checkpoint-a", node="node_b", count=2)])
    repository = _PromotingRepository(thread)
    reconciler = ThreadCheckpointReconciler(
        repository,
        store,
        node_order=("node_a", "node_b"),
        scan_limit=10,
        max_checkpoint_bytes=1_048_576,
        worker_consumer="worker-2",
    )

    promoted = await reconciler.reconcile(thread)

    assert promoted.current_checkpoint_id == "checkpoint-b"
    assert promoted.state_version == 2
    assert repository.commands[0].event_type.value == "RECONCILIATION"
    assert store.limits == [10]


@pytest.mark.asyncio
async def test_orphan_checkpoint_not_canonical():
    thread = _canonical_a()
    store = _RecordStore([_record("checkpoint-b", parent_id="checkpoint-a", node="node_b", count=2)])
    repository = _PromotingRepository(thread)

    records = await store.list_bounded(thread.thread_id, 10)

    assert records[0].checkpoint_id == "checkpoint-b"
    assert repository.thread.current_checkpoint_id == "checkpoint-a"
    assert repository.commands == []


@pytest.mark.asyncio
async def test_divergent_orphans_not_auto_promoted():
    thread = _canonical_a()
    store = _RecordStore(
        [
            _record("checkpoint-b1", parent_id="checkpoint-a", node="node_b", count=2),
            _record("checkpoint-b2", parent_id="checkpoint-a", node="node_b", count=2),
        ]
    )
    repository = _PromotingRepository(thread)
    reconciler = ThreadCheckpointReconciler(
        repository,
        store,
        node_order=("node_a", "node_b"),
        scan_limit=10,
        max_checkpoint_bytes=1_048_576,
        worker_consumer="worker-2",
    )

    with pytest.raises(RuntimeThreadCheckpointError, match="DIVERGENT_ORPHAN_CHECKPOINTS"):
        await reconciler.reconcile(thread)

    assert repository.commands == []


@pytest.mark.asyncio
async def test_reconcile_only_once():
    thread = _canonical_a()
    store = _RecordStore([_record("checkpoint-b", parent_id="checkpoint-a", node="node_b", count=2)])
    repository = _PromotingRepository(thread)
    reconciler = ThreadCheckpointReconciler(
        repository,
        store,
        node_order=("node_a", "node_b"),
        scan_limit=10,
        max_checkpoint_bytes=1_048_576,
        worker_consumer="worker-2",
    )

    first = await reconciler.reconcile(thread)
    second = await reconciler.reconcile(first)

    assert first == second
    assert len(repository.commands) == 1


@pytest.mark.asyncio
async def test_checkpoint_size_limit():
    thread = _canonical_a()
    store = _RecordStore(
        [_record("checkpoint-b", parent_id="checkpoint-a", node="node_b", count=2, size=1_048_577)]
    )
    repository = _PromotingRepository(thread)
    reconciler = ThreadCheckpointReconciler(
        repository,
        store,
        node_order=("node_a", "node_b"),
        scan_limit=10,
        max_checkpoint_bytes=1_048_576,
        worker_consumer="worker-2",
    )

    with pytest.raises(RuntimeThreadCheckpointError, match="CHECKPOINT_PAYLOAD_TOO_LARGE"):
        await reconciler.reconcile(thread)

    assert repository.commands == []


@pytest.mark.asyncio
async def test_runner_rejects_noncontinuous_checkpoint_before_next_node():
    counters = {"node_a": 0, "node_b": 0}

    class Graph:
        async def astream(self, state, **kwargs):
            counters["node_a"] += 1
            yield {"node_a": {"last_completed_node": "node_a", "completed_node_count": 1}}
            counters["node_b"] += 1
            yield {"node_b": {"last_completed_node": "node_b", "completed_node_count": 2}}

    repository = _PromotingRepository(_thread())
    store = _RecordStore([_record("checkpoint-wrong", parent_id="unexpected-parent", node="node_a", count=7)])
    runner = CheckpointedGraphRunner(
        Graph(),
        repository,
        store,
        node_order=("node_a", "node_b"),
        max_checkpoint_bytes=1_048_576,
        worker_consumer="worker-1",
    )

    with pytest.raises(RuntimeThreadCheckpointError, match="CHECKPOINT_BOUNDARY_MISSING"):
        await runner.run_new(_thread(), {"value": 0})

    assert counters == {"node_a": 1, "node_b": 0}
    assert repository.commands == []


@pytest.mark.asyncio
async def test_first_checkpoint_requires_a_complete_initial_ancestry():
    class Graph:
        async def astream(self, state, **kwargs):
            yield {"node_a": {"last_completed_node": "node_a", "completed_node_count": 1}}

    repository = _PromotingRepository(_thread())
    store = _RecordStore([_record("checkpoint-rogue", parent_id="missing-root", node="node_a", count=1)])
    runner = CheckpointedGraphRunner(
        Graph(),
        repository,
        store,
        node_order=("node_a", "node_b"),
        max_checkpoint_bytes=1_048_576,
        worker_consumer="worker-1",
    )

    with pytest.raises(RuntimeThreadCheckpointError, match="CHECKPOINT_BOUNDARY_MISSING"):
        await runner.run_new(_thread(), {"value": 0})

    assert repository.commands == []


@pytest.mark.asyncio
async def test_first_orphan_reconciliation_rejects_a_missing_initial_ancestor():
    thread = _thread()
    repository = _PromotingRepository(thread)
    reconciler = ThreadCheckpointReconciler(
        repository,
        _RecordStore([_record("checkpoint-rogue", parent_id="missing-root", node="node_a", count=1)]),
        node_order=("node_a", "node_b"),
        scan_limit=10,
        max_checkpoint_bytes=1_048_576,
        worker_consumer="worker-2",
    )

    reconciled = await reconciler.reconcile(thread)

    assert reconciled == thread
    assert repository.commands == []
