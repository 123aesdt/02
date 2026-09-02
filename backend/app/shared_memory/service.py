import asyncio
from collections.abc import Callable
from datetime import datetime

from app.observability.recorder import MetricsRecorder, NoOpMetricsRecorder
from app.shared_memory.identity import (
    build_fact_key,
    content_fingerprint,
    evidence_fingerprint,
    payload_fingerprint,
)
from app.shared_memory.models import (
    MemoryCategory,
    MemoryMutationResult,
    MemoryTarget,
    MutationDecision,
    MutationStatus,
    ProjectionStatus,
    SharedMemoryMutationCommand,
)
from app.shared_memory.policy import MemoryDecision, MemoryPolicySettings, evaluate_mutation
from app.shared_memory.protocols import MemoryFingerprints, StoredMutation


class MemoryMutationBusy(Exception):
    def __init__(self, fact_key: str) -> None:
        super().__init__("Another mutation is already changing this memory fact")
        self.fact_key = fact_key


class MemoryMutationValidationError(ValueError):
    pass


class SharedMemoryMutationService:
    def __init__(
        self,
        *,
        repository: object,
        lock: object,
        policy_settings: MemoryPolicySettings,
        vector_projection: object,
        graph_projection: object,
        projection_builder: object,
        event_publisher: object,
        clock: Callable[[], datetime],
        timeout_seconds: float = 5.0,
        projection_timeout_seconds: float | None = None,
        metrics: MetricsRecorder | None = None,
    ) -> None:
        self._repository = repository
        self._lock = lock
        self._policy_settings = policy_settings
        self._vector_projection = vector_projection
        self._graph_projection = graph_projection
        self._projection_builder = projection_builder
        self._events = event_publisher
        self._clock = clock
        self._timeout_seconds = timeout_seconds
        self.metrics = metrics or NoOpMetricsRecorder()
        self._projection_timeout_seconds = (
            projection_timeout_seconds
            if projection_timeout_seconds is not None
            else min(2.0, timeout_seconds * 0.4)
        )
        if self._projection_timeout_seconds <= 0 or self._projection_timeout_seconds >= timeout_seconds:
            raise ValueError("projection timeout must be positive and shorter than mutation timeout")

    async def mutate(self, command: SharedMemoryMutationCommand) -> MemoryMutationResult:
        self._validate_command(command)
        fingerprints = self._fingerprints(command)
        handle = await self._lock.acquire(fingerprints.fact_key)
        if not handle.acquired:
            raise MemoryMutationBusy(fingerprints.fact_key)
        try:
            async with asyncio.timeout(self._timeout_seconds):
                result = await self._mutate_locked(command, fingerprints)
                self._record_mutation(result)
                return result
        finally:
            await self._lock.release(handle)

    async def _mutate_locked(
        self,
        command: SharedMemoryMutationCommand,
        fingerprints: MemoryFingerprints,
    ) -> MemoryMutationResult:
        begun = self._repository.begin_or_replay(command, fingerprints)
        if begun.replayed:
            return self._result(self._repository.get_mutation(begun.mutation_id))

        await self._publish("MEMORY_MUTATION_REQUESTED", begun.mutation_id, fingerprints.fact_key)
        current = self._repository.load_fact(fingerprints.fact_key)
        decision = evaluate_mutation(
            current,
            command,
            self._policy_settings,
            now=self._clock(),
        )
        stored = self._repository.record_decision(begun.mutation_id, decision)
        self._repository.append_evidence(begun.mutation_id, command, fingerprints)

        if not decision.requires_projection:
            if (
                decision.decision is MutationDecision.CONFLICT_REVIEW
                and current is None
            ):
                self._repository.create_pending_review(
                    begun.mutation_id,
                    command,
                    fingerprints,
                    now=self._clock(),
                )
            result = self._result(self._repository.get_mutation(begun.mutation_id))
            await self._publish_terminal(result)
            return result

        self._repository.mark_applying(begun.mutation_id)
        version = decision.after_version
        if version is None:
            raise RuntimeError("Projection decision requires an after_version")

        vector_spec = None
        graph_spec = None
        if MemoryTarget.VECTOR in command.targets:
            vector_spec = await self._projection_builder.build_vector(
                command,
                begun.mutation_id,
                fingerprints.fact_key,
                version,
            )
            vector_error = await self._stage_projection(
                begun.mutation_id,
                MemoryTarget.VECTOR,
                self._vector_projection,
                vector_spec,
            )
        else:
            vector_error = None
        if MemoryTarget.GRAPH in command.targets:
            graph_spec = await self._projection_builder.build_graph(
                command,
                begun.mutation_id,
                fingerprints.fact_key,
                version,
            )
            graph_error = await self._stage_projection(
                begun.mutation_id,
                MemoryTarget.GRAPH,
                self._graph_projection,
                graph_spec,
            )
        else:
            graph_error = None

        if vector_error or graph_error:
            return await self._finish_partial(
                begun.mutation_id,
                vector_error or graph_error or "PROJECTION_STAGE_FAILED",
            )

        self._repository.finalize_canonical(
            begun.mutation_id,
            command,
            fingerprints,
            decision,
            now=self._clock(),
        )

        if vector_spec is not None:
            vector_error = await self._activate_projection(
                begun.mutation_id,
                MemoryTarget.VECTOR,
                self._vector_projection,
                vector_spec,
            )
        if graph_spec is not None:
            graph_error = await self._activate_projection(
                begun.mutation_id,
                MemoryTarget.GRAPH,
                self._graph_projection,
                graph_spec,
            )

        if vector_error or graph_error:
            return await self._finish_partial(
                begun.mutation_id,
                vector_error or graph_error or "PROJECTION_ACTIVATE_FAILED",
            )

        stored = self._repository.mark_applied(begun.mutation_id, now=self._clock())
        self._repository.append_attempt(
            begun.mutation_id,
            result=MutationStatus.APPLIED.value,
            vector_after=stored.vector_status,
            graph_after=stored.graph_status,
        )
        result = self._result(stored)
        await self._publish_terminal(result)
        return result

    async def resume_mutation(self, mutation_id: str) -> MemoryMutationResult:
        stored = self._repository.get_mutation(mutation_id)
        if stored.status in {
            MutationStatus.APPLIED.value,
            MutationStatus.REJECTED.value,
            MutationStatus.CONFLICT.value,
            MutationStatus.FAILED.value,
        }:
            return self._result(stored)
        handle = await self._lock.acquire(stored.fact_key)
        if not handle.acquired:
            raise MemoryMutationBusy(stored.fact_key)
        try:
            async with asyncio.timeout(self._timeout_seconds):
                result = await self._resume_locked(stored)
                reconciliation_result = {
                    MutationStatus.APPLIED: "success",
                    MutationStatus.CONFLICT: "conflict",
                    MutationStatus.FAILED: "failed",
                }.get(result.status, "noop")
                self.metrics.increment("countyflow_memory_reconciliations_total", {"result": reconciliation_result})
                self._record_mutation(result)
                return result
        finally:
            await self._lock.release(handle)

    def get_mutation_result(self, mutation_id: str) -> MemoryMutationResult:
        return self._result(self._repository.get_mutation(mutation_id))

    def get_fact_detail(self, fact_key: str) -> dict[str, object]:
        return self._repository.get_fact_detail(fact_key)

    def _record_mutation(self, result: MemoryMutationResult) -> None:
        self.metrics.increment(
            "countyflow_memory_mutations_total",
            {"decision": result.decision.value, "result": result.status.value},
        )

    async def _resume_locked(self, stored: StoredMutation) -> MemoryMutationResult:
        command = SharedMemoryMutationCommand.from_dict(stored.proposed_fact_json)
        fingerprints = self._fingerprints(command)
        if fingerprints.fact_key != stored.fact_key:
            raise MemoryMutationValidationError("Stored memory mutation identity is invalid")
        if stored.decision is None or stored.after_version is None:
            raise MemoryMutationValidationError("Stored memory mutation decision is incomplete")
        decision = MemoryDecision(
            decision=MutationDecision(stored.decision),
            reason_code=stored.reason_code or "RESUME",
            before_version=stored.before_version,
            after_version=stored.after_version,
            proposed_status=self._proposed_status(command),
            requires_projection=True,
        )
        self._repository.mark_applying(stored.mutation_id)
        version = stored.after_version
        vector_spec = None
        graph_spec = None
        errors: list[str] = []

        if MemoryTarget.VECTOR in command.targets:
            vector_spec = await self._projection_builder.build_vector(
                command, stored.mutation_id, stored.fact_key, version
            )
            state = await self._vector_projection.probe(stored.mutation_id, version)
            if state in {ProjectionStatus.STAGED.value, ProjectionStatus.ACTIVE.value}:
                self._repository.update_projection_status(
                    stored.mutation_id, MemoryTarget.VECTOR, state
                )
            else:
                error = await self._stage_projection(
                    stored.mutation_id,
                    MemoryTarget.VECTOR,
                    self._vector_projection,
                    vector_spec,
                )
                if error:
                    errors.append(error)

        if MemoryTarget.GRAPH in command.targets:
            graph_spec = await self._projection_builder.build_graph(
                command, stored.mutation_id, stored.fact_key, version
            )
            state = await self._graph_projection.probe(stored.mutation_id, version)
            if state in {ProjectionStatus.STAGED.value, ProjectionStatus.ACTIVE.value}:
                self._repository.update_projection_status(
                    stored.mutation_id, MemoryTarget.GRAPH, state
                )
            else:
                error = await self._stage_projection(
                    stored.mutation_id,
                    MemoryTarget.GRAPH,
                    self._graph_projection,
                    graph_spec,
                )
                if error:
                    errors.append(error)

        if errors:
            return await self._finish_partial(stored.mutation_id, errors[0])

        self._repository.finalize_canonical(
            stored.mutation_id,
            command,
            fingerprints,
            decision,
            now=self._clock(),
        )

        if vector_spec is not None:
            state = await self._vector_projection.probe(stored.mutation_id, version)
            if state != ProjectionStatus.ACTIVE.value:
                error = await self._activate_projection(
                    stored.mutation_id,
                    MemoryTarget.VECTOR,
                    self._vector_projection,
                    vector_spec,
                )
                if error:
                    errors.append(error)
        if graph_spec is not None:
            state = await self._graph_projection.probe(stored.mutation_id, version)
            if state != ProjectionStatus.ACTIVE.value:
                error = await self._activate_projection(
                    stored.mutation_id,
                    MemoryTarget.GRAPH,
                    self._graph_projection,
                    graph_spec,
                )
                if error:
                    errors.append(error)

        if errors:
            return await self._finish_partial(stored.mutation_id, errors[0])

        applied = self._repository.mark_applied(stored.mutation_id, now=self._clock())
        self._repository.append_attempt(
            stored.mutation_id,
            result=MutationStatus.APPLIED.value,
            vector_before=stored.vector_status,
            vector_after=applied.vector_status,
            graph_before=stored.graph_status,
            graph_after=applied.graph_status,
        )
        result = self._result(applied)
        await self._publish_terminal(result)
        return result

    async def _stage_projection(
        self,
        mutation_id: str,
        target: MemoryTarget,
        port: object,
        projection: object,
    ) -> str | None:
        try:
            async with asyncio.timeout(self._projection_timeout_seconds):
                await port.stage(projection)
        except TimeoutError:
            self._repository.update_projection_status(
                mutation_id,
                target,
                ProjectionStatus.FAILED.value,
            )
            return "PROJECTION_TIMEOUT"
        except Exception as error:
            if isinstance(error, asyncio.CancelledError):
                raise
            self._repository.update_projection_status(
                mutation_id,
                target,
                ProjectionStatus.FAILED.value,
            )
            return self._safe_error_code(error)
        self._repository.update_projection_status(
            mutation_id,
            target,
            ProjectionStatus.STAGED.value,
        )
        return None

    async def _activate_projection(
        self,
        mutation_id: str,
        target: MemoryTarget,
        port: object,
        projection: object,
    ) -> str | None:
        try:
            async with asyncio.timeout(self._projection_timeout_seconds):
                await port.activate(projection)
                await port.retire_previous(projection)
        except TimeoutError:
            return "PROJECTION_TIMEOUT"
        except Exception as error:
            if isinstance(error, asyncio.CancelledError):
                raise
            return self._safe_error_code(error)
        self._repository.update_projection_status(
            mutation_id,
            target,
            ProjectionStatus.ACTIVE.value,
        )
        return None

    async def _finish_partial(self, mutation_id: str, error_code: str) -> MemoryMutationResult:
        stored = self._repository.mark_partial(
            mutation_id,
            error_code=error_code,
            error_summary="A required memory projection is incomplete",
        )
        self._repository.append_attempt(
            mutation_id,
            result=MutationStatus.PARTIAL.value,
            vector_after=stored.vector_status,
            graph_after=stored.graph_status,
            error_code=error_code,
            error_summary="A required memory projection is incomplete",
        )
        result = self._result(stored)
        await self._publish_terminal(result)
        return result

    @staticmethod
    def _safe_error_code(error: Exception) -> str:
        value = str(error)
        if value and len(value) <= 64 and all(character.isupper() or character.isdigit() or character == "_" for character in value):
            return value
        return "PROJECTION_OPERATION_FAILED"

    @staticmethod
    def _proposed_status(command: SharedMemoryMutationCommand):
        from app.shared_memory.models import MemoryFactStatus

        return MemoryFactStatus.ACTIVE

    @staticmethod
    def _validate_command(command: SharedMemoryMutationCommand) -> None:
        if command.category is not MemoryCategory.DISPATCH:
            raise MemoryMutationValidationError("V2-B accepts DispatchMemory only")
        allowed = {
            "ATTRIBUTE": frozenset({MemoryTarget.GRAPH}),
            "RELATIONSHIP": frozenset({MemoryTarget.GRAPH}),
            "EXPERIENCE": frozenset({MemoryTarget.VECTOR}),
            "HYBRID": frozenset({MemoryTarget.VECTOR, MemoryTarget.GRAPH}),
        }[command.fact_kind.value]
        if command.targets != allowed:
            raise MemoryMutationValidationError("Memory targets do not match the fact-kind registry")

    @staticmethod
    def _fingerprints(command: SharedMemoryMutationCommand) -> MemoryFingerprints:
        return MemoryFingerprints(
            fact_key=build_fact_key(command),
            content_fingerprint=content_fingerprint(command),
            payload_fingerprint=payload_fingerprint(command),
            evidence_fingerprint=evidence_fingerprint(command),
        )

    @staticmethod
    def _result(stored: StoredMutation) -> MemoryMutationResult:
        return MemoryMutationResult(
            mutation_id=stored.mutation_id,
            fact_key=stored.fact_key,
            decision=MutationDecision(stored.decision),
            status=MutationStatus(stored.status),
            before_version=stored.before_version,
            after_version=stored.after_version,
            vector_status=ProjectionStatus(stored.vector_status),
            graph_status=ProjectionStatus(stored.graph_status),
            projection_incomplete=stored.status in {"PARTIAL", "FINALIZING"},
            error_code=stored.error_code,
            error_summary=stored.error_summary,
        )

    async def _publish(self, event_type: str, mutation_id: str, fact_key: str) -> None:
        await self._events.publish(
            event_type,
            {"mutation_id": mutation_id, "fact_key": fact_key},
        )

    async def _publish_terminal(self, result: MemoryMutationResult) -> None:
        event_type = {
            MutationStatus.APPLIED: "MEMORY_MUTATION_APPLIED",
            MutationStatus.REJECTED: "MEMORY_MUTATION_REJECTED",
            MutationStatus.CONFLICT: "MEMORY_MUTATION_CONFLICT",
            MutationStatus.PARTIAL: "MEMORY_MUTATION_PARTIAL",
        }[result.status]
        await self._events.publish(
            event_type,
            {
                "mutation_id": result.mutation_id,
                "fact_key": result.fact_key,
                "decision": result.decision.value,
                "status": result.status.value,
                "before_version": result.before_version,
                "after_version": result.after_version,
                "vector_status": result.vector_status.value,
                "graph_status": result.graph_status.value,
            },
        )
