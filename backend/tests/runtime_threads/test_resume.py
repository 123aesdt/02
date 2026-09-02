from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NotRequired, TypedDict

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.agents.audit import audit_node
from app.agents.dispatch import dispatch_node
from app.audit.service import AuditService
from app.dispatch.service import DispatchService
from app.graph.state import DispatchGraphState
from app.idempotency.service import IdempotencyService
from app.models.audit import AuditRecord
from app.models.base import Base
from app.models.dispatch import Dispatch
from app.models.order import Order
from app.models.shared_memory import MemoryMutation
from app.runtime_threads.checkpoint_store import RedisRuntimeCheckpointStore
from app.runtime_threads.models import RuntimeThreadSnapshot, RuntimeThreadStatus
from app.runtime_threads.runner import CheckpointedGraphRunner, RuntimeThreadCheckpointError
from app.runtime_threads.sqlalchemy_repository import SqlAlchemyRuntimeThreadRepository


class _State(TypedDict):
    value: int
    last_completed_node: NotRequired[str]
    completed_node_count: NotRequired[int]


def _thread() -> RuntimeThreadSnapshot:
    now = datetime.now(UTC)
    return RuntimeThreadSnapshot(
        thread_id="cf:dispatch:TASK-3123456789abcdef0123456789abcde",
        task_id="TASK-3123456789abcdef0123456789abcde",
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


class _Repository:
    def __init__(self, thread):
        self.thread = thread
        self.promotions = []
        self.resume_keys = set()

    def promote_checkpoint(self, command):
        self.promotions.append(command)
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

    def mark_resumed(self, thread_id, event_key, worker_consumer):
        assert thread_id == self.thread.thread_id
        if event_key not in self.resume_keys:
            self.resume_keys.add(event_key)
            self.thread = replace(
                self.thread,
                resumed_count=self.thread.resumed_count + 1,
                worker_consumer=worker_consumer,
            )
        return self.thread


def _graph(saver, counters):
    def node(name, count):
        async def run(state: _State):
            counters[name] += 1
            return {
                "value": state["value"] + 1,
                "last_completed_node": name,
                "completed_node_count": count,
            }

        return run

    graph = StateGraph(_State)
    graph.add_node("node_a", node("node_a", 1))
    graph.add_node("node_b", node("node_b", 2))
    graph.add_node("node_c", node("node_c", 3))
    graph.add_edge(START, "node_a")
    graph.add_edge("node_a", "node_b")
    graph.add_edge("node_b", "node_c")
    graph.add_edge("node_c", END)
    return graph.compile(checkpointer=saver, interrupt_after=["node_b"])


async def _checkpoint_after_b():
    saver = InMemorySaver()
    counters = {"node_a": 0, "node_b": 0, "node_c": 0}
    repository = _Repository(_thread())
    store = RedisRuntimeCheckpointStore(saver)
    first_runner = CheckpointedGraphRunner(
        _graph(saver, counters),
        repository,
        store,
        node_order=("node_a", "node_b", "node_c"),
        max_checkpoint_bytes=1_048_576,
        worker_consumer="worker-1",
    )
    await first_runner.run_new(repository.thread, {"value": 0})
    return saver, counters, repository, store


@pytest.mark.asyncio
async def test_resume_from_latest_checkpoint():
    saver, counters, repository, store = await _checkpoint_after_b()
    checkpoint_b = repository.thread.current_checkpoint_id
    resumed_runner = CheckpointedGraphRunner(
        _graph(saver, counters),
        repository,
        store,
        node_order=("node_a", "node_b", "node_c"),
        max_checkpoint_bytes=1_048_576,
        worker_consumer="worker-2",
    )

    result = await resumed_runner.resume(repository.thread)

    assert checkpoint_b is not None
    assert result["value"] == 3
    assert repository.thread.current_node == "node_c"
    assert repository.thread.resumed_count == 1
    assert repository.thread.worker_consumer == "worker-2"


@pytest.mark.asyncio
async def test_resume_does_not_repeat_completed_nodes():
    saver, counters, repository, store = await _checkpoint_after_b()
    before_resume = counters.copy()
    resumed_runner = CheckpointedGraphRunner(
        _graph(saver, counters),
        repository,
        store,
        node_order=("node_a", "node_b", "node_c"),
        max_checkpoint_bytes=1_048_576,
        worker_consumer="worker-2",
    )

    await resumed_runner.resume(repository.thread, resume_key="1-0:2:worker-2")

    assert before_resume == {"node_a": 1, "node_b": 1, "node_c": 0}
    assert counters == {"node_a": 1, "node_b": 1, "node_c": 1}
    assert len(repository.resume_keys) == 1
    assert repository.resume_keys == {f"resume:{repository.promotions[-2].checkpoint_id}:1-0:2:worker-2"}


@pytest.mark.asyncio
async def test_terminal_thread_resume_is_rejected():
    saver = InMemorySaver()
    counters = {"node_a": 0, "node_b": 0, "node_c": 0}
    repository = _Repository(replace(_thread(), status=RuntimeThreadStatus.TERMINAL, current_checkpoint_id="checkpoint-final"))
    runner = CheckpointedGraphRunner(
        _graph(saver, counters),
        repository,
        RedisRuntimeCheckpointStore(saver),
        node_order=("node_a", "node_b", "node_c"),
        max_checkpoint_bytes=1_048_576,
        worker_consumer="worker-2",
    )

    with pytest.raises(RuntimeThreadCheckpointError, match="RUNTIME_THREAD_TERMINAL"):
        await runner.resume(repository.thread)

    assert counters == {"node_a": 0, "node_b": 0, "node_c": 0}


def _business_database():
    temp = TemporaryDirectory(dir=Path(__file__).parent)
    engine = create_engine(f"sqlite+pysqlite:///{Path(temp.name) / 'resume.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(Order(order_no="ORD-RUNTIME-RESUME", status="open", origin="A", destination="B"))
        session.commit()
    IdempotencyService(factory).begin(
        "TASK-4123456789abcdef0123456789abcde",
        1,
        "idem-runtime-resume",
    )
    return temp, engine, factory


def _business_graph(saver, factory, *, interrupt_after):
    async def dispatch(state: DispatchGraphState):
        patch = await dispatch_node(state, DispatchService(factory))
        return {**patch, "last_completed_node": "dispatch", "completed_node_count": 1}

    async def audit(state: DispatchGraphState):
        patch = await audit_node(state, AuditService(factory))
        return {**patch, "last_completed_node": "audit", "completed_node_count": 2}

    graph = StateGraph(DispatchGraphState)
    graph.add_node("dispatch", dispatch)
    graph.add_node("audit", audit)
    graph.add_edge(START, "dispatch")
    graph.add_edge("dispatch", "audit")
    graph.add_edge("audit", END)
    return graph.compile(checkpointer=saver, interrupt_after=interrupt_after)


def _business_state():
    return {
        "task_id": "TASK-4123456789abcdef0123456789abcde",
        "order_id": 1,
        "driver_id": "driver-li",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "雨天道路湿滑",
        "recommended_route": "national-102",
        "decision": "REROUTE",
        "decision_reason": "safer",
        "fallback_used": False,
        "requires_manual_review": False,
    }


def _business_runner(saver, factory, graph, worker):
    repository = SqlAlchemyRuntimeThreadRepository(factory)
    return (
        CheckpointedGraphRunner(
            graph,
            repository,
            RedisRuntimeCheckpointStore(saver),
            node_order=("dispatch", "audit"),
            max_checkpoint_bytes=1_048_576,
            worker_consumer=worker,
        ),
        repository,
    )


@pytest.mark.asyncio
async def test_resume_no_duplicate_dispatch():
    temp, engine, factory = _business_database()
    saver = InMemorySaver()
    try:
        first, repository = _business_runner(
            saver,
            factory,
            _business_graph(saver, factory, interrupt_after=["dispatch"]),
            "worker-1",
        )
        thread = replace(repository.get_by_task_id("TASK-4123456789abcdef0123456789abcde"), next_node="dispatch")
        await first.run_new(thread, _business_state())
        resumed, repository = _business_runner(
            saver,
            factory,
            _business_graph(saver, factory, interrupt_after=["dispatch"]),
            "worker-2",
        )
        await resumed.resume(repository.get_by_task_id(thread.task_id))
        with factory() as session:
            dispatch_count = session.scalar(select(func.count()).select_from(Dispatch))
            audit_count = session.scalar(select(func.count()).select_from(AuditRecord))
            mutation_count = session.scalar(select(func.count()).select_from(MemoryMutation))

        assert (dispatch_count, audit_count, mutation_count) == (1, 1, 0)
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_resume_no_duplicate_audit():
    temp, engine, factory = _business_database()
    saver = InMemorySaver()
    try:
        first, repository = _business_runner(
            saver,
            factory,
            _business_graph(saver, factory, interrupt_after=["audit"]),
            "worker-1",
        )
        thread = replace(repository.get_by_task_id("TASK-4123456789abcdef0123456789abcde"), next_node="dispatch")
        await first.run_new(thread, _business_state())
        resumed, repository = _business_runner(
            saver,
            factory,
            _business_graph(saver, factory, interrupt_after=["audit"]),
            "worker-2",
        )
        await resumed.resume(repository.get_by_task_id(thread.task_id))
        with factory() as session:
            dispatch_count = session.scalar(select(func.count()).select_from(Dispatch))
            audit_count = session.scalar(select(func.count()).select_from(AuditRecord))
            mutation_count = session.scalar(select(func.count()).select_from(MemoryMutation))

        assert (dispatch_count, audit_count, mutation_count) == (1, 1, 0)
    finally:
        engine.dispose()
        temp.cleanup()
