import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.audit.service import AuditService
from app.capacity.models import CapacitySnapshot
from app.capacity.provider import InMemoryCapacityProvider
from app.capacity.service import CapacityService
from app.dispatch.service import DispatchService
from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.idempotency.service import IdempotencyService
from app.locks.redis_execution_lock import RedisExecutionLock
from app.models.audit import AuditRecord
from app.models.base import Base
from app.models.dispatch import Dispatch
from app.models.order import Order
from app.providers.environment import EnvironmentResult, StaticRouteFallbackProvider
from app.runtime_threads.models import RuntimeThreadSnapshot, RuntimeThreadStatus
from app.services.circuit_breaker import CircuitBreaker
from app.services.environment import EnvironmentService
from app.streams.models import DispatchTaskMessage, StreamMessage
from app.streams.redis_queue import RedisStreamQueue
from app.workers.dispatch_worker import DispatchWorker
from tests.graph.test_routing_agent import _memory_service, _routing_service


@pytest_asyncio.fixture
async def redis_client():
    client = FakeRedis(decode_responses=False)
    yield client
    await client.aclose()


def _database() -> tuple[TemporaryDirectory, object, sessionmaker]:
    temp = TemporaryDirectory()
    engine = create_engine(f"sqlite+pysqlite:///{Path(temp.name) / 'worker-idempotency.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(Order(order_no="ORD-WORKER-IDEMPOTENCY", status="open", origin="A", destination="B"))
        session.commit()
    return temp, engine, factory


def _task(task_id: str = "task-001") -> DispatchTaskMessage:
    return DispatchTaskMessage(
        schema_version="1",
        task_id=task_id,
        order_id=1,
        anomaly_id=10,
        idempotency_key=f"idem-{task_id}",
        created_at="2026-08-21T00:00:00+00:00",
        payload={
            "driver_id": "driver-li",
            "vehicle_id": "vehicle-001",
            "route_id": "xinping-road",
            "anomaly_type": "rain_slippery",
            "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
        },
    )


def _message(message_id: str = "1-0", task: DispatchTaskMessage | None = None) -> StreamMessage:
    return StreamMessage(message_id, task or _task(), None, {"stream": "worker-idempotency"})


class _Queue:
    def __init__(self) -> None:
        self.acked: list[str] = []

    async def ack(self, message_id: str) -> int:
        self.acked.append(message_id)
        return 1


class _ApprovedGraph:
    def __init__(self) -> None:
        self.invocations = 0

    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        self.invocations += 1
        return {"audit_result": {"audit_status": "APPROVED"}, "requires_manual_review": False}


class _FailingGraph:
    def __init__(self) -> None:
        self.invocations = 0

    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        self.invocations += 1
        raise RuntimeError("graph failed")


def _worker(queue: _Queue, graph: object, factory: sessionmaker, redis_client: FakeRedis, *, ttl_ms: int = 1000) -> DispatchWorker:
    return DispatchWorker(
        queue,
        graph,
        read_count=1,
        block_ms=1,
        idempotency_service=IdempotencyService(factory),
        execution_lock=RedisExecutionLock(redis_client, ttl_ms=ttl_ms),
    )


@pytest.mark.asyncio
async def test_worker_new_task_executes_graph(redis_client: FakeRedis):
    temp, engine, factory = _database()
    try:
        queue = _Queue()
        graph = _ApprovedGraph()

        result = await _worker(queue, graph, factory, redis_client).process_message(_message())

        assert (graph.invocations, result.acknowledged, result.idempotency_state) == (1, True, "NEW")
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_worker_startup_initializes_checkpoint_store_before_consuming():
    events: list[str] = []

    class Runner:
        async def setup(self):
            events.append("setup")

    worker = DispatchWorker(_Queue(), _ApprovedGraph(), read_count=1, block_ms=1, runtime_runner=Runner())

    await worker.startup()

    assert events == ["setup"]


@pytest.mark.asyncio
async def test_worker_uses_runtime_runner_and_terminalizes_before_ack(redis_client: FakeRedis):
    temp, engine, factory = _database()
    events: list[str] = []

    class RuntimeRepository:
        def __init__(self):
            self.thread = None

        def get_by_task_id(self, task_id):
            if self.thread is None:
                now = __import__("datetime").datetime.now(__import__("datetime").UTC)
                self.thread = RuntimeThreadSnapshot(
                    thread_id=f"cf:dispatch:{task_id}",
                    task_id=task_id,
                    status=RuntimeThreadStatus.RUNNING,
                    current_checkpoint_id=None,
                    state_version=0,
                    current_node=None,
                    next_node="intake",
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
            return self.thread

        def mark_terminal(self, thread_id, **kwargs):
            events.append("thread_terminal")
            self.thread = self.thread.__class__(
                **{**self.thread.__dict__, "status": RuntimeThreadStatus.TERMINAL, "next_node": None}
            )
            return self.thread

    class RuntimeRunner:
        async def setup(self):
            events.append("checkpoint_setup")

        async def run_new(self, thread, state):
            events.append("run_new")
            return {"audit_result": {"audit_status": "APPROVED"}, "requires_manual_review": False}

        async def resume(self, thread, *, resume_key=None):
            raise AssertionError("new threads must not resume")

        async def publish_terminal(self, thread):
            events.append("thread_terminal_event")

    class OrderedIdempotencyService(IdempotencyService):
        def mark_terminal(self, task_id, status):
            events.append("task_terminal")
            return super().mark_terminal(task_id, status)

    class OrderedQueue(_Queue):
        async def ack(self, message_id):
            events.append("ack")
            return await super().ack(message_id)

    try:
        repository = RuntimeRepository()
        worker = DispatchWorker(
            OrderedQueue(),
            _ApprovedGraph(),
            read_count=1,
            block_ms=1,
            consumer_name="worker-runtime",
            idempotency_service=OrderedIdempotencyService(factory),
            execution_lock=RedisExecutionLock(redis_client, ttl_ms=1000),
            runtime_runner=RuntimeRunner(),
            runtime_thread_repository=repository,
        )

        result = await worker.process_message(_message())

        assert result.acknowledged is True
        assert events == [
            "checkpoint_setup",
            "run_new",
            "thread_terminal",
            "task_terminal",
            "thread_terminal_event",
            "ack",
        ]
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_worker_claims_stable_boundary_before_resuming_next_node(redis_client: FakeRedis):
    temp, engine, factory = _database()
    events: list[str] = []
    now = __import__("datetime").datetime.now(__import__("datetime").UTC)

    class RuntimeRepository:
        def __init__(self):
            self.thread = RuntimeThreadSnapshot(
                thread_id="cf:dispatch:task-001",
                task_id="task-001",
                status=RuntimeThreadStatus.RUNNING,
                current_checkpoint_id=None,
                state_version=0,
                current_node=None,
                next_node="intake",
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

        def get_by_task_id(self, task_id):
            return self.thread

        def claim_next_node(self, thread_id, **kwargs):
            events.append("claim_capacity")
            assert kwargs == {
                "expected_checkpoint_id": "checkpoint-c7",
                "expected_state_version": 7,
                "expected_next_node": "capacity",
                "worker_consumer": "worker-runtime",
            }
            self.thread = self.thread.__class__(
                **{**self.thread.__dict__, "status": RuntimeThreadStatus.RUNNING}
            )
            return self.thread

        def mark_terminal(self, thread_id, **kwargs):
            events.append("thread_terminal")
            self.thread = self.thread.__class__(
                **{**self.thread.__dict__, "status": RuntimeThreadStatus.TERMINAL, "next_node": None}
            )
            return self.thread

    repository = RuntimeRepository()

    class RuntimeRunner:
        async def setup(self):
            return None

        async def run_new(self, thread, state):
            events.append("environment_boundary")
            repository.thread = repository.thread.__class__(
                **{
                    **repository.thread.__dict__,
                    "status": RuntimeThreadStatus.STABLE,
                    "current_checkpoint_id": "checkpoint-c7",
                    "state_version": 7,
                    "current_node": "environment",
                    "next_node": "capacity",
                }
            )
            return {"vehicle_status": "NORMAL", "last_completed_node": "environment"}

        async def resume(self, thread, *, resume_key=None):
            events.append("capacity_resume")
            repository.thread = repository.thread.__class__(
                **{
                    **repository.thread.__dict__,
                    "status": RuntimeThreadStatus.STABLE,
                    "current_checkpoint_id": "checkpoint-final",
                    "state_version": 8,
                    "current_node": "audit",
                    "next_node": None,
                }
            )
            return {"audit_result": {"audit_status": "APPROVED"}, "requires_manual_review": False}

        async def publish_terminal(self, thread):
            return None

    try:
        worker = DispatchWorker(
            _Queue(),
            _ApprovedGraph(),
            read_count=1,
            block_ms=1,
            consumer_name="worker-runtime",
            idempotency_service=IdempotencyService(factory),
            execution_lock=RedisExecutionLock(redis_client, ttl_ms=1000),
            runtime_runner=RuntimeRunner(),
            runtime_thread_repository=repository,
        )

        paused = await worker.process_message(_message())
        result = await worker.process_message(_message())

        assert paused.error_code == "RUNTIME_THREAD_PAUSED"
        assert result.acknowledged is True
        assert events[:3] == ["environment_boundary", "claim_capacity", "capacity_resume"]
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_worker_never_uses_noncanonical_override_checkpoint(redis_client: FakeRedis):
    temp, engine, factory = _database()
    now = __import__("datetime").datetime.now(__import__("datetime").UTC)
    canonical = RuntimeThreadSnapshot(
        thread_id="cf:dispatch:task-001", task_id="task-001", status=RuntimeThreadStatus.STABLE,
        current_checkpoint_id="checkpoint-c7", state_version=7, current_node="environment", next_node="capacity",
        checkpoint_count=4, checkpoint_size_bytes=512, last_event_sequence=None, worker_consumer="worker-1",
        resumed_count=0, created_at=now, updated_at=now, terminal_at=None, row_version=7,
    )

    class Repository:
        def __init__(self):
            self.thread = canonical
            self.claimed = False

        def get_by_task_id(self, task_id):
            return self.thread

        def claim_next_node(self, thread_id, **kwargs):
            assert kwargs["expected_checkpoint_id"] == "checkpoint-c7"
            self.claimed = True
            self.thread = self.thread.__class__(**{**self.thread.__dict__, "status": RuntimeThreadStatus.RUNNING})
            return self.thread

        def mark_terminal(self, thread_id, **kwargs):
            self.thread = self.thread.__class__(
                **{**self.thread.__dict__, "status": RuntimeThreadStatus.TERMINAL, "next_node": None}
            )
            return self.thread

    repository = Repository()

    class Runner:
        async def setup(self):
            return None

        async def resume(self, thread, *, resume_key=None):
            # Redis also contains C8, but the worker can only receive MySQL's exact C7 pointer.
            assert thread.current_checkpoint_id == "checkpoint-c7"
            repository.thread = repository.thread.__class__(
                **{**repository.thread.__dict__, "current_checkpoint_id": "checkpoint-final", "next_node": None}
            )
            return {"audit_result": {"audit_status": "APPROVED"}, "requires_manual_review": False}

        async def publish_terminal(self, thread):
            return None

    try:
        result = await DispatchWorker(
            _Queue(), _ApprovedGraph(), read_count=1, block_ms=1, consumer_name="worker-runtime",
            idempotency_service=IdempotencyService(factory),
            execution_lock=RedisExecutionLock(redis_client, ttl_ms=1000),
            runtime_runner=Runner(), runtime_thread_repository=repository,
        ).process_message(_message())
        assert result.acknowledged is True
        assert repository.claimed is True
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_runtime_reconciliation_failure_leaves_message_pending(redis_client: FakeRedis):
    temp, engine, factory = _database()

    class Repository:
        def get_by_task_id(self, task_id):
            now = __import__("datetime").datetime.now(__import__("datetime").UTC)
            return RuntimeThreadSnapshot(
                thread_id=f"cf:dispatch:{task_id}", task_id=task_id, status=RuntimeThreadStatus.STABLE,
                current_checkpoint_id="checkpoint-1", state_version=1, current_node="intake", next_node="entity_memory",
                checkpoint_count=1, checkpoint_size_bytes=512, last_event_sequence=None, worker_consumer="worker-1",
                resumed_count=0, created_at=now, updated_at=now, terminal_at=None, row_version=1,
            )

    class FailingReconciler:
        async def reconcile(self, thread):
            raise RuntimeError("redis://credential-must-not-escape")

    try:
        queue = _Queue()
        worker = DispatchWorker(
            queue,
            _ApprovedGraph(),
            read_count=1,
            block_ms=1,
            idempotency_service=IdempotencyService(factory),
            execution_lock=RedisExecutionLock(redis_client, ttl_ms=1000),
            runtime_thread_repository=Repository(),
            runtime_thread_reconciler=FailingReconciler(),
        )

        result = await worker.process_message(_message())

        assert result.error_code == "RUNTIME_THREAD_RECONCILIATION_ERROR"
        assert result.acknowledged is False
        assert queue.acked == []
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_worker_terminal_replay_skips_graph(redis_client: FakeRedis):
    temp, engine, factory = _database()
    try:
        ledger = IdempotencyService(factory)
        ledger.begin("task-001", 1, "idem-task-001")
        ledger.mark_terminal("task-001", "APPROVED")
        graph = _ApprovedGraph()

        result = await _worker(_Queue(), graph, factory, redis_client).process_message(_message())

        assert (graph.invocations, result.duplicate_skipped, result.idempotency_state) == (0, True, "TERMINAL")
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_worker_terminal_replay_is_acked(redis_client: FakeRedis):
    temp, engine, factory = _database()
    try:
        ledger = IdempotencyService(factory)
        ledger.begin("task-001", 1, "idem-task-001")
        ledger.mark_terminal("task-001", "APPROVED")
        queue = _Queue()

        result = await _worker(queue, _ApprovedGraph(), factory, redis_client).process_message(_message())

        assert (result.acknowledged, queue.acked) == (True, ["1-0"])
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_two_workers_same_idempotency_key_only_one_executes(redis_client: FakeRedis):
    temp, engine, factory = _database()
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingGraph:
        def __init__(self) -> None:
            self.invocations = 0

        async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
            self.invocations += 1
            started.set()
            await release.wait()
            return {"audit_result": {"audit_status": "APPROVED"}, "requires_manual_review": False}

    try:
        graph = BlockingGraph()
        worker_a = _worker(_Queue(), graph, factory, redis_client)
        worker_b = _worker(_Queue(), graph, factory, redis_client)
        task_a = asyncio.create_task(worker_a.process_message(_message("1-0")))
        await started.wait()
        result_b = await worker_b.process_message(_message("2-0"))
        release.set()
        await task_a

        assert (graph.invocations, result_b.acknowledged, result_b.lock_acquired) == (1, False, False)
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_worker_lock_contention_does_not_execute_graph(redis_client: FakeRedis):
    temp, engine, factory = _database()
    try:
        lock = RedisExecutionLock(redis_client, ttl_ms=1000)
        await lock.acquire("idem-task-001")
        graph = _ApprovedGraph()

        result = await _worker(_Queue(), graph, factory, redis_client).process_message(_message())

        assert (graph.invocations, result.terminal_status, result.acknowledged) == (0, "LOCKED", False)
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_recovery_after_terminal_before_ack_skips_graph(redis_client: FakeRedis):
    temp, engine, factory = _database()
    stream = "countyflow:idempotency:recovery"
    group = "idempotency-recovery-workers"
    try:
        ledger = IdempotencyService(factory)
        ledger.begin("task-001", 1, "idem-task-001")
        ledger.mark_terminal("task-001", "APPROVED")
        queue_a = RedisStreamQueue(redis_client, stream, group, "worker-a")
        queue_b = RedisStreamQueue(redis_client, stream, group, "worker-b")
        await queue_a.ensure_consumer_group()
        await queue_a.publish(_task())
        await queue_a.read_group(count=1, block_ms=1)
        await asyncio.sleep(1.1)
        graph = _ApprovedGraph()
        worker = DispatchWorker(
            queue_b,
            graph,
            read_count=1,
            block_ms=1,
            pending_min_idle_ms=1,
            recovery_count=1,
            idempotency_service=ledger,
            execution_lock=RedisExecutionLock(redis_client, ttl_ms=1000),
        )

        [result] = await worker.recover_once()

        assert (graph.invocations, result.acknowledged, (await redis_client.xpending(stream, group))["pending"]) == (0, True, 0)
    finally:
        engine.dispose()
        temp.cleanup()


class _RainEnvironmentProvider:
    async def get_environment(self, route_id: str) -> EnvironmentResult:
        return EnvironmentResult("heavy_rain", "slippery", "high", "test_environment", False, None, 1.0)


async def _real_graph(factory: sessionmaker):
    return build_graph(
        GraphDependencies(
            entity_memory_service=await _memory_service(),
            environment_service=EnvironmentService(_RainEnvironmentProvider(), StaticRouteFallbackProvider(), CircuitBreaker(3, 5.0)),
            capacity_service=CapacityService(
                InMemoryCapacityProvider({("driver-li", "vehicle-001"): CapacitySnapshot(True, True, 0.45, 0.60, "in_memory_capacity")}),
                limited_threshold=0.8,
                unavailable_threshold=1.0,
            ),
            routing_service=_routing_service(),
            dispatch_service=DispatchService(factory),
            audit_service=AuditService(factory),
        )
    )


@pytest.mark.asyncio
async def test_recovery_after_dispatch_commit_does_not_duplicate_dispatch(redis_client: FakeRedis):
    temp, engine, factory = _database()
    try:
        ledger = IdempotencyService(factory)
        ledger.begin("task-001", 1, "idem-task-001")
        ledger.mark_processing("task-001")
        DispatchService(factory).execute("task-001", 1, "xinping-road", "national-102", "REROUTE", "safer", False, None, False)

        result = await _worker(_Queue(), await _real_graph(factory), factory, redis_client).process_message(_message())
        with factory() as session:
            dispatch_count = session.scalar(select(func.count()).select_from(Dispatch))
            audit_count = session.scalar(select(func.count()).select_from(AuditRecord))

        assert (result.acknowledged, dispatch_count, audit_count) == (True, 1, 1)
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_recovery_after_dispatch_commit_completes_missing_audit(redis_client: FakeRedis):
    temp, engine, factory = _database()
    try:
        ledger = IdempotencyService(factory)
        ledger.begin("task-001", 1, "idem-task-001")
        ledger.mark_processing("task-001")
        DispatchService(factory).execute("task-001", 1, "xinping-road", "national-102", "REROUTE", "safer", False, None, False)

        await _worker(_Queue(), await _real_graph(factory), factory, redis_client).process_message(_message())
        with factory() as session:
            audit = session.scalar(select(AuditRecord))

        assert audit.result == "APPROVED"
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_duplicate_message_does_not_duplicate_audit(redis_client: FakeRedis):
    temp, engine, factory = _database()
    try:
        real_graph = await _real_graph(factory)

        class CountingGraph:
            def __init__(self) -> None:
                self.invocations = 0

            async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
                self.invocations += 1
                return await real_graph.ainvoke(state)

        graph = CountingGraph()
        worker = _worker(_Queue(), graph, factory, redis_client)
        await worker.process_message(_message("1-0"))
        await worker.process_message(_message("2-0"))
        with factory() as session:
            dispatch_count = session.scalar(select(func.count()).select_from(Dispatch))
            audit_count = session.scalar(select(func.count()).select_from(AuditRecord))

        assert (graph.invocations, dispatch_count, audit_count) == (1, 1, 1)
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_execution_lock_released_after_success(redis_client: FakeRedis):
    temp, engine, factory = _database()
    try:
        task = _task()
        await _worker(_Queue(), _ApprovedGraph(), factory, redis_client).process_message(_message(task=task))

        handle = await RedisExecutionLock(redis_client, ttl_ms=1000).acquire(task.idempotency_key)
        assert handle.acquired is True
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_execution_lock_released_after_failure(redis_client: FakeRedis):
    temp, engine, factory = _database()
    try:
        task = _task()
        await _worker(_Queue(), _FailingGraph(), factory, redis_client).process_message(_message(task=task))

        handle = await RedisExecutionLock(redis_client, ttl_ms=1000).acquire(task.idempotency_key)
        assert handle.acquired is True
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_cancelled_worker_does_not_release_other_workers_lock(redis_client: FakeRedis):
    temp, engine, factory = _database()
    started = asyncio.Event()
    cancel = asyncio.Event()
    try:
        class DelayedCancelledGraph:
            async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
                started.set()
                await cancel.wait()
                raise asyncio.CancelledError

        worker = _worker(_Queue(), DelayedCancelledGraph(), factory, redis_client, ttl_ms=10)
        running = asyncio.create_task(worker.process_message(_message()))
        await started.wait()
        await asyncio.sleep(0.05)
        other_lock = RedisExecutionLock(redis_client, ttl_ms=1000)
        other_handle = await other_lock.acquire("idem-task-001")
        cancel.set()
        with pytest.raises(asyncio.CancelledError):
            await running

        third_handle = await RedisExecutionLock(redis_client, ttl_ms=1000).acquire("idem-task-001")
        assert (other_handle.acquired, third_handle.acquired) == (True, False)
        await other_lock.release(other_handle)
    finally:
        engine.dispose()
        temp.cleanup()
