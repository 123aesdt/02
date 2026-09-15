import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from typing import Protocol

from app.events.broker import TaskEventBroker
from app.events.graph_adapter import GraphEventAdapter
from app.events.models import TaskEvent, TaskEventType
from app.graph.state import DispatchGraphState
from app.idempotency.service import IdempotencyService
from app.locks.redis_execution_lock import ExecutionLockError, LockHandle, RedisExecutionLock
from app.observability.context import bind_observability_context
from app.observability.labels import WORKERS
from app.observability.recorder import MetricsRecorder, NoOpMetricsRecorder
from app.runtime_threads.models import BoundaryClaimConflict, RuntimeThreadSnapshot, RuntimeThreadStatus
from app.runtime_threads.protocols import RuntimeThreadRepository
from app.streams.errors import QueueMessageError
from app.streams.models import DispatchTaskMessage, StreamMessage
from app.streams.redis_queue import RedisStreamQueue
from app.streams.retry import RetryPolicy

PENDING_RECOVERY_START_ID = "0-0"
DEFAULT_RETRY_POLICY = RetryPolicy(
    max_delivery_attempts=3,
    base_delay_ms=1000,
    max_delay_ms=30_000,
)
SleepFunction = Callable[[float], Awaitable[None]]


class CompiledGraph(Protocol):
    async def ainvoke(self, state: DispatchGraphState) -> Mapping[str, object]: ...


class RuntimeGraphRunner(Protocol):
    async def setup(self) -> None: ...

    async def run_new(self, thread: RuntimeThreadSnapshot, state: DispatchGraphState) -> Mapping[str, object]: ...

    async def resume(
        self,
        thread: RuntimeThreadSnapshot,
        *,
        resume_key: str | None = None,
    ) -> Mapping[str, object]: ...

    async def close(self) -> None: ...

    async def publish_terminal(self, thread: RuntimeThreadSnapshot) -> None: ...


class RuntimeThreadReconciler(Protocol):
    async def reconcile(self, thread: RuntimeThreadSnapshot) -> RuntimeThreadSnapshot: ...


class AutomaticPublicationService(Protocol):
    def publish_automatically(self, task_id: str) -> Mapping[str, object]: ...


class VehicleBreakdownHandler(Protocol):
    def handle_approved_breakdown(self, message: DispatchTaskMessage) -> None: ...


@dataclass(frozen=True)
class WorkerProcessResult:
    message_id: str
    task_id: str
    acknowledged: bool
    terminal_status: str | None
    requires_manual_review: bool
    error_code: str | None
    delivery_count: int | None = None
    retried: bool = False
    moved_to_dlq: bool = False
    backoff_ms: int | None = None
    idempotency_state: str | None = None
    duplicate_skipped: bool = False
    lock_acquired: bool | None = None
    reconciled: bool = False


def task_message_to_graph_input(task: DispatchTaskMessage) -> DispatchGraphState:
    state: DispatchGraphState = {
        "task_id": task.task_id,
        "order_id": task.order_id,
        "driver_id": task.payload["driver_id"],
        "vehicle_id": task.payload["vehicle_id"],
        "route_id": task.payload["route_id"],
        "anomaly_type": task.payload["anomaly_type"],
        "anomaly_description": task.payload["anomaly_description"],
        "vehicle_status": task.payload.get("vehicle_status", "NORMAL"),
    }
    if task.correlation_id is not None:
        state["correlation_id"] = task.correlation_id
    return state


class DispatchWorker:
    def __init__(
        self,
        queue: RedisStreamQueue,
        graph: CompiledGraph,
        *,
        read_count: int,
        block_ms: int,
        consumer_name: str = "worker-1",
        pending_min_idle_ms: int = 5000,
        recovery_count: int = 10,
        retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
        sleep_func: SleepFunction = asyncio.sleep,
        idempotency_service: IdempotencyService | None = None,
        execution_lock: RedisExecutionLock | None = None,
        event_broker: TaskEventBroker | None = None,
        runtime_runner: RuntimeGraphRunner | None = None,
        runtime_thread_repository: RuntimeThreadRepository | None = None,
        runtime_thread_reconciler: RuntimeThreadReconciler | None = None,
        automatic_publication_service: AutomaticPublicationService | None = None,
        vehicle_breakdown_handler: VehicleBreakdownHandler | None = None,
        logger: logging.Logger | None = None,
        metrics: MetricsRecorder | None = None,
    ) -> None:
        self._queue = queue
        self._graph = graph
        self._read_count = read_count
        self._block_ms = block_ms
        self._consumer_name = consumer_name
        self._pending_min_idle_ms = pending_min_idle_ms
        self._recovery_count = recovery_count
        self._retry_policy = retry_policy
        self._sleep_func = sleep_func
        self._idempotency_service = idempotency_service
        self._execution_lock = execution_lock
        self._event_broker = event_broker
        self._runtime_runner = runtime_runner
        self._runtime_thread_repository = runtime_thread_repository
        self._runtime_thread_reconciler = runtime_thread_reconciler
        self._automatic_publication_service = automatic_publication_service
        self._vehicle_breakdown_handler = vehicle_breakdown_handler
        self._logger = logger or logging.getLogger(__name__)
        self._metrics = metrics or NoOpMetricsRecorder()
        self._stop_event = asyncio.Event()

    async def run_once(self) -> list[WorkerProcessResult]:
        await self._queue.ensure_consumer_group()
        try:
            messages = await self._queue.read_group(
                count=self._read_count,
                block_ms=self._block_ms,
            )
        except QueueMessageError:
            self._logger.warning("Invalid Redis stream message was left pending.")
            return []
        results: list[WorkerProcessResult] = []
        for message in messages:
            with bind_observability_context(correlation_id=message.task.correlation_id):
                results.append(await self.process_message(message))
        for result in results:
            self._record_result(result)
        await self._sample_queue_state()
        return results

    async def startup(self) -> None:
        if self._runtime_runner is not None:
            await self._runtime_runner.setup()

    async def _recover_message(self, message: StreamMessage) -> WorkerProcessResult:
        delivery_count = message.delivery_count
        if delivery_count is None:
            self._logger.warning(
                "Recovered message has no delivery count; leaving it pending. message_id=%s",
                message.message_id,
            )
            return WorkerProcessResult(
                message.message_id,
                message.task.task_id,
                False,
                None,
                False,
                "DELIVERY_COUNT_UNAVAILABLE",
            )

        if not self._retry_policy.should_retry(delivery_count):
            if await self._execution_is_active(message):
                return WorkerProcessResult(
                    message.message_id,
                    message.task.task_id,
                    False,
                    "LOCKED",
                    False,
                    None,
                    delivery_count=delivery_count,
                    lock_acquired=False,
                )
            terminal_thread = await self._mark_runtime_terminal(
                message.task.task_id,
                "DLQ",
                "MAX_DELIVERY_ATTEMPTS_EXCEEDED",
            )
            if terminal_thread is None:
                return WorkerProcessResult(
                    message.message_id,
                    message.task.task_id,
                    False,
                    None,
                    False,
                    "RUNTIME_THREAD_TERMINAL_ERROR",
                    delivery_count=delivery_count,
                )
            if self._idempotency_service is not None:
                self._idempotency_service.mark_terminal(message.task.task_id, "DLQ")
            await self._publish_runtime_terminal(terminal_thread)
            await self._publish(
                message.task.task_id,
                TaskEventType.TASK_FAILED,
                "worker",
                "DLQ",
                {"error_code": "MAX_DELIVERY_ATTEMPTS_EXCEEDED"},
            )
            await self._queue.move_to_dlq(
                message,
                "Maximum delivery attempts exceeded.",
                "MAX_DELIVERY_ATTEMPTS_EXCEEDED",
                delivery_count=delivery_count,
            )
            return WorkerProcessResult(
                message.message_id,
                message.task.task_id,
                True,
                "DLQ",
                False,
                "MAX_DELIVERY_ATTEMPTS_EXCEEDED",
                delivery_count=delivery_count,
                moved_to_dlq=True,
            )

        backoff_ms = self._retry_policy.backoff_ms(delivery_count)
        await self._sleep_func(backoff_ms / 1000)
        return replace(
            await self.process_message(message),
            delivery_count=delivery_count,
            retried=True,
            backoff_ms=backoff_ms,
        )

    async def _execution_is_active(self, message: StreamMessage) -> bool:
        if self._execution_lock is None:
            return False
        probe = await self._execution_lock.acquire(message.task.idempotency_key)
        if not probe.acquired:
            return True
        await self._execution_lock.release(probe)
        return False

    async def process_message(self, message: StreamMessage) -> WorkerProcessResult:
        if self._idempotency_service is None or self._execution_lock is None:
            requires_post_processing = self._automatic_publication_service is not None or self._vehicle_breakdown_handler is not None
            result = await self._process_graph(
                message,
                acknowledge_terminal=not requires_post_processing,
            )
            if requires_post_processing and result.terminal_status in {"APPROVED", "REVIEW_REQUIRED"}:
                publication_error = self._auto_publish(message.task.task_id, result.terminal_status)
                if publication_error is not None:
                    return replace(result, acknowledged=False, error_code=publication_error)
                vehicle_error = self._handle_vehicle_breakdown(message.task, result.terminal_status)
                if vehicle_error is not None:
                    return replace(result, acknowledged=False, error_code=vehicle_error)
                acknowledged = await self._queue.ack(message.message_id) == 1
                result = replace(result, acknowledged=acknowledged)
            await self._publish_terminal(message.task.task_id, result)
            return result

        lock_handle = await self._execution_lock.acquire(message.task.idempotency_key)
        if not lock_handle.acquired:
            return WorkerProcessResult(
                message.message_id,
                message.task.task_id,
                False,
                "LOCKED",
                False,
                None,
                lock_acquired=False,
            )

        renewal_task = asyncio.create_task(self._maintain_execution_lock(lock_handle))
        try:
            decision = self._idempotency_service.begin(
                message.task.task_id,
                message.task.order_id,
                message.task.idempotency_key,
            )
            if decision.state == "TERMINAL":
                terminal_thread = await self._mark_runtime_terminal(
                    message.task.task_id,
                    decision.existing_status or "COMPLETED",
                )
                if terminal_thread is None:
                    return self._runtime_terminal_failure(message, decision.state)
                await self._publish_runtime_terminal(terminal_thread)
                return await self._ack_terminal_replay(message, decision.existing_status, reconciled=False)
            if decision.state == "IN_PROGRESS":
                reconciliation = self._idempotency_service.reconcile_existing_execution(message.task.task_id)
                if reconciliation.is_terminal:
                    terminal_thread = await self._mark_runtime_terminal(
                        message.task.task_id,
                        reconciliation.terminal_status or "COMPLETED",
                    )
                    if terminal_thread is None:
                        return self._runtime_terminal_failure(message, decision.state)
                    self._idempotency_service.mark_terminal(message.task.task_id, reconciliation.terminal_status or "COMPLETED")
                    await self._publish_runtime_terminal(terminal_thread)
                    return await self._ack_terminal_replay(message, reconciliation.terminal_status, reconciled=True)
            else:
                self._idempotency_service.mark_processing(message.task.task_id)

            try:
                runtime_thread = await self._runtime_thread(message.task.task_id)
            except Exception:
                self._logger.warning(
                    "Runtime thread reconciliation failed. task_id=%s",
                    message.task.task_id,
                )
                return WorkerProcessResult(
                    message.message_id,
                    message.task.task_id,
                    False,
                    None,
                    False,
                    "RUNTIME_THREAD_RECONCILIATION_ERROR",
                    idempotency_state=decision.state,
                    lock_acquired=True,
                )
            result = await self._process_graph(
                message,
                acknowledge_terminal=False,
                runtime_thread=runtime_thread,
            )
            if result.terminal_status not in {"APPROVED", "REVIEW_REQUIRED"}:
                await self._publish_terminal(message.task.task_id, result)
                return replace(result, idempotency_state=decision.state, lock_acquired=True)
            terminal_thread = await self._mark_runtime_terminal(message.task.task_id, result.terminal_status)
            if terminal_thread is None:
                return self._runtime_terminal_failure(message, decision.state)
            self._idempotency_service.mark_terminal(message.task.task_id, result.terminal_status)
            publication_error = self._auto_publish(message.task.task_id, result.terminal_status)
            if publication_error is not None:
                return replace(result, acknowledged=False, error_code=publication_error, idempotency_state=decision.state, lock_acquired=True)
            vehicle_error = self._handle_vehicle_breakdown(message.task, result.terminal_status)
            if vehicle_error is not None:
                return replace(result, acknowledged=False, error_code=vehicle_error, idempotency_state=decision.state, lock_acquired=True)
            await self._publish_runtime_terminal(terminal_thread)
            await self._publish_terminal(message.task.task_id, result)
            acknowledged = await self._queue.ack(message.message_id) == 1
            terminal_result = replace(
                result,
                acknowledged=acknowledged,
                idempotency_state=decision.state,
                lock_acquired=True,
            )
            return terminal_result
        finally:
            renewal_task.cancel()
            try:
                await renewal_task
            except asyncio.CancelledError:
                pass
            await self._execution_lock.release(lock_handle)

    async def _maintain_execution_lock(self, handle: LockHandle) -> None:
        if self._execution_lock is None:
            return
        while True:
            await asyncio.sleep(self._execution_lock.renewal_interval_seconds)
            try:
                renewed = await self._execution_lock.renew(handle)
            except ExecutionLockError:
                self._logger.warning("Dispatch execution lock renewal failed. key=%s", handle.key)
                return
            if not renewed:
                return

    async def _ack_terminal_replay(
        self,
        message: StreamMessage,
        status: str | None,
        *,
        reconciled: bool,
    ) -> WorkerProcessResult:
        publication_error = self._auto_publish(message.task.task_id, status)
        if publication_error is not None:
            return WorkerProcessResult(
                message.message_id,
                message.task.task_id,
                False,
                status,
                False,
                publication_error,
                idempotency_state="TERMINAL",
                lock_acquired=True,
                reconciled=reconciled,
            )
        vehicle_error = self._handle_vehicle_breakdown(message.task, status)
        if vehicle_error is not None:
            return WorkerProcessResult(
                message.message_id,
                message.task.task_id,
                False,
                status,
                False,
                vehicle_error,
                idempotency_state="TERMINAL",
                lock_acquired=True,
                reconciled=reconciled,
            )
        acknowledged = await self._queue.ack(message.message_id) == 1
        return WorkerProcessResult(
            message.message_id,
            message.task.task_id,
            acknowledged,
            status,
            status == "REVIEW_REQUIRED",
            None,
            idempotency_state="TERMINAL",
            duplicate_skipped=True,
            lock_acquired=True,
            reconciled=reconciled,
        )

    def _auto_publish(self, task_id: str, terminal_status: str | None) -> str | None:
        if terminal_status != "APPROVED" or self._automatic_publication_service is None:
            return None
        try:
            self._automatic_publication_service.publish_automatically(task_id)
        except Exception:
            self._logger.exception(
                "Approved dispatch automatic publication failed. task_id=%s",
                task_id,
            )
            return "AUTO_PUBLICATION_ERROR"
        return None

    def _handle_vehicle_breakdown(
        self,
        message: DispatchTaskMessage,
        terminal_status: str | None,
    ) -> str | None:
        if (
            terminal_status != "APPROVED"
            or self._vehicle_breakdown_handler is None
            or str(message.payload.get("anomaly_type", "")).upper() != "VEHICLE_BREAKDOWN"
        ):
            return None
        try:
            self._vehicle_breakdown_handler.handle_approved_breakdown(message)
        except Exception:
            self._logger.exception(
                "Vehicle rescue orchestration failed. task_id=%s",
                message.task_id,
            )
            return "VEHICLE_RESCUE_ORCHESTRATION_ERROR"
        return None

    async def _process_graph(
        self,
        message: StreamMessage,
        *,
        acknowledge_terminal: bool,
        runtime_thread: RuntimeThreadSnapshot | None = None,
    ) -> WorkerProcessResult:
        started_at = time.perf_counter()
        await self._publish(
            message.task.task_id,
            TaskEventType.WORKER_STARTED,
            "worker",
            "PROCESSING",
            {"consumer_name": self._consumer_name, "message_id": message.message_id},
        )
        try:
            graph_input = task_message_to_graph_input(message.task)
            if self._runtime_runner is not None and runtime_thread is not None:
                await self._runtime_runner.setup()
                if runtime_thread.current_checkpoint_id is None:
                    final_state = await self._runtime_runner.run_new(runtime_thread, graph_input)
                else:
                    if runtime_thread.status is RuntimeThreadStatus.STABLE:
                        if self._runtime_thread_repository is None or runtime_thread.next_node is None:
                            raise BoundaryClaimConflict("RUNTIME_BOUNDARY_CLAIM_CONFLICT")
                        runtime_thread = self._runtime_thread_repository.claim_next_node(
                            runtime_thread.thread_id,
                            expected_checkpoint_id=runtime_thread.current_checkpoint_id,
                            expected_state_version=runtime_thread.state_version,
                            expected_next_node=runtime_thread.next_node,
                            worker_consumer=self._consumer_name,
                        )
                    final_state = await self._runtime_runner.resume(
                        runtime_thread,
                        resume_key=f"{message.message_id}:{message.delivery_count or 1}:{self._consumer_name}",
                    )
            elif self._event_broker is not None and hasattr(self._graph, "astream"):
                final_state = await GraphEventAdapter(self._event_broker).invoke(self._graph, graph_input)
            else:
                final_state = await self._graph.ainvoke(graph_input)
        except asyncio.CancelledError:
            self._logger.info("Dispatch worker task cancelled before terminal persistence.")
            raise
        except Exception:
            self._logger.exception("Dispatch worker graph execution failed.")
            await self._publish(message.task.task_id, TaskEventType.TASK_FAILED, "worker", "FAILED", {"error_code": "GRAPH_EXECUTION_ERROR"})
            return WorkerProcessResult(
                message.message_id,
                message.task.task_id,
                False,
                "FAILED",
                False,
                "GRAPH_EXECUTION_ERROR",
            )

        terminal_status, requires_manual_review, error_code = self._terminal_state(final_state)
        if terminal_status is None:
            if self._runtime_thread_repository is not None:
                paused = self._runtime_thread_repository.get_by_task_id(message.task.task_id)
                if paused is not None and paused.status is RuntimeThreadStatus.STABLE and paused.next_node is not None:
                    return WorkerProcessResult(
                        message.message_id,
                        message.task.task_id,
                        False,
                        None,
                        False,
                        "RUNTIME_THREAD_PAUSED",
                    )
            await self._publish(message.task.task_id, TaskEventType.TASK_FAILED, "audit", "FAILED", {"error_code": error_code})
            return WorkerProcessResult(
                message.message_id,
                message.task.task_id,
                False,
                None,
                requires_manual_review,
                error_code,
            )
        acknowledged = await self._queue.ack(message.message_id) == 1 if acknowledge_terminal else False
        self._logger.info(
            "Dispatch worker terminal result task_id=%s message_id=%s consumer_name=%s terminal_status=%s acknowledged=%s elapsed_ms=%.2f",
            message.task.task_id,
            message.message_id,
            self._consumer_name,
            terminal_status,
            acknowledged,
            (time.perf_counter() - started_at) * 1000,
        )
        return WorkerProcessResult(
            message.message_id,
            message.task.task_id,
            acknowledged,
            terminal_status,
            requires_manual_review,
            error_code,
        )

    async def _runtime_thread(self, task_id: str) -> RuntimeThreadSnapshot | None:
        if self._runtime_thread_repository is None:
            return None
        thread = self._runtime_thread_repository.get_by_task_id(task_id)
        if thread is not None and self._runtime_thread_reconciler is not None:
            thread = await self._runtime_thread_reconciler.reconcile(thread)
        return thread

    async def _mark_runtime_terminal(
        self,
        task_id: str,
        status: str,
        error_code: str | None = None,
    ) -> RuntimeThreadSnapshot | bool | None:
        if self._runtime_thread_repository is None:
            return True
        thread = self._runtime_thread_repository.get_by_task_id(task_id)
        if thread is None:
            return None
        try:
            terminal_thread = self._runtime_thread_repository.mark_terminal(
                thread.thread_id,
                event_key=f"terminal:{status}",
                worker_consumer=self._consumer_name,
                current_node=thread.current_node,
                error_code=error_code,
            )
        except Exception:
            self._logger.exception("Runtime thread terminal persistence failed.")
            return False
        return terminal_thread

    async def _publish_runtime_terminal(self, thread: RuntimeThreadSnapshot | bool) -> None:
        if isinstance(thread, RuntimeThreadSnapshot) and self._runtime_runner is not None and hasattr(self._runtime_runner, "publish_terminal"):
            await self._runtime_runner.publish_terminal(thread)

    @staticmethod
    def _runtime_terminal_failure(message: StreamMessage, idempotency_state: str) -> WorkerProcessResult:
        return WorkerProcessResult(
            message.message_id,
            message.task.task_id,
            False,
            None,
            False,
            "RUNTIME_THREAD_TERMINAL_ERROR",
            idempotency_state=idempotency_state,
            lock_acquired=True,
        )

    async def _publish_terminal(self, task_id: str, result: WorkerProcessResult) -> None:
        if result.terminal_status == "APPROVED":
            await self._publish(task_id, TaskEventType.TASK_COMPLETED, "audit", "COMPLETED", {})
        elif result.terminal_status == "REVIEW_REQUIRED":
            await self._publish(task_id, TaskEventType.TASK_REVIEW_REQUIRED, "audit", "REVIEW_REQUIRED", {})

    async def _publish(
        self,
        task_id: str,
        event_type: TaskEventType,
        node: str,
        status: str,
        data: Mapping[str, object],
    ) -> None:
        if self._event_broker is None:
            return
        try:
            await self._event_broker.publish(TaskEvent.create(task_id, event_type, node, status, data=data))
        except Exception:
            self._logger.debug("Task event publication failed without affecting worker execution.")

    async def recover_once(self) -> list[WorkerProcessResult]:
        await self._queue.ensure_consumer_group()
        recovery_scan_started_epoch_ms = time.time() * 1000
        recovery_scan_started = time.perf_counter()
        try:
            messages = await self._queue.claim_pending(
                consumer_name=self._consumer_name,
                min_idle_ms=self._pending_min_idle_ms,
                start_id=PENDING_RECOVERY_START_ID,
                count=self._recovery_count,
            )
        except QueueMessageError:
            self._logger.warning("Invalid Redis pending message was left pending.")
            return []
        if messages:
            self._logger.warning(
                "Dispatch worker claimed pending messages consumer_name=%s message_ids=%s task_ids=%s "
                "recovery_scan_started_epoch_ms=%.3f xautoclaim_elapsed_ms=%.3f",
                self._consumer_name,
                ",".join(message.message_id for message in messages),
                ",".join(message.task.task_id for message in messages),
                recovery_scan_started_epoch_ms,
                (time.perf_counter() - recovery_scan_started) * 1000,
            )
        results: list[WorkerProcessResult] = []
        for message in messages:
            claim_started = time.perf_counter()
            with bind_observability_context(correlation_id=message.task.correlation_id):
                result = await self._recover_message(message)
            results.append(result)
            self._record_result(result)
            self._metrics.increment("countyflow_worker_messages_total", {"worker": self._consumer_name, "result": "recovered"})
            try:
                pending_idle_seconds = int(message.metadata.get("pending_idle_ms_at_claim", "0")) / 1000
            except ValueError:
                pending_idle_seconds = 0
            recovery_seconds = pending_idle_seconds + (time.perf_counter() - claim_started)
            self._metrics.observe(
                "countyflow_worker_recovery_duration_seconds",
                recovery_seconds,
                {"worker": self._consumer_name},
            )
            if recovery_seconds > 5:
                self._metrics.increment("countyflow_worker_recovery_slo_breaches_total", {"worker": self._consumer_name})
        await self._sample_queue_state()
        return results

    async def _sample_queue_state(self) -> None:
        getter = getattr(self._queue, "get_operational_state", None)
        if getter is None:
            return
        try:
            state = await getter()
        except Exception:
            return
        for worker in WORKERS:
            self._metrics.set_gauge(
                "countyflow_worker_pending_messages",
                state.pending_by_consumer.get(worker, 0),
                {"worker": worker},
            )
        self._metrics.set_gauge("countyflow_worker_stream_lag", state.stream_lag)
        self._metrics.set_gauge("countyflow_worker_dlq_messages", state.dlq_messages)

    def _record_result(self, result: WorkerProcessResult) -> None:
        labels = {"worker": self._consumer_name}
        self._metrics.increment("countyflow_worker_messages_total", {**labels, "result": "processed"})
        if result.acknowledged:
            self._metrics.increment("countyflow_worker_messages_total", {**labels, "result": "acked"})
        if result.retried:
            self._metrics.increment("countyflow_worker_messages_total", {**labels, "result": "retried"})
        if result.moved_to_dlq:
            self._metrics.increment("countyflow_worker_messages_total", {**labels, "result": "dlq"})
            self._metrics.increment("countyflow_worker_dlq_total", labels)
        if result.error_code and not result.acknowledged:
            self._metrics.increment("countyflow_worker_messages_total", {**labels, "result": "failed"})

    async def run_forever(self) -> None:
        while not self._stop_event.is_set():
            await self.run_once()

    async def shutdown(self) -> None:
        self._stop_event.set()
        if self._runtime_runner is not None and hasattr(self._runtime_runner, "close"):
            await self._runtime_runner.close()
        await self._queue.close()

    @staticmethod
    def _terminal_state(final_state: Mapping[str, object]) -> tuple[str | None, bool, str | None]:
        error_code = final_state.get("error_code")
        safe_error_code = error_code if isinstance(error_code, str) else None
        requires_manual_review = final_state.get("requires_manual_review") is True
        if safe_error_code == "AUDIT_PERSISTENCE_ERROR":
            return None, requires_manual_review, safe_error_code
        audit_result = final_state.get("audit_result")
        if not isinstance(audit_result, Mapping):
            return None, requires_manual_review, safe_error_code
        audit_status = audit_result.get("audit_status")
        if audit_status == "APPROVED":
            return "APPROVED", requires_manual_review, safe_error_code
        if audit_status == "REVIEW_REQUIRED" and requires_manual_review:
            return "REVIEW_REQUIRED", True, safe_error_code
        return None, requires_manual_review, safe_error_code
