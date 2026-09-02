from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.models.shared_memory import (
    MemoryEvidence,
    MemoryMutation,
    MemoryMutationAttempt,
    SharedMemoryFact,
)
from app.shared_memory.models import (
    MemoryFactStatus,
    MemoryTarget,
    MutationStatus,
    ProjectionStatus,
    SharedMemoryMutationCommand,
)
from app.shared_memory.policy import MemoryDecision, MemoryVersionConflict, SharedMemoryFactSnapshot
from app.shared_memory.protocols import BeginMutationResult, MemoryFingerprints, StoredMutation


class MemoryIdempotencyConflict(Exception):
    def __init__(self, idempotency_key: str) -> None:
        super().__init__("Idempotency key was already used for a different memory mutation")
        self.idempotency_key = idempotency_key


class MemoryProjectionIncomplete(Exception):
    def __init__(self, mutation_id: str) -> None:
        super().__init__("All required memory projections must be active before APPLIED")
        self.mutation_id = mutation_id


class SqlAlchemyMemoryControlRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def begin_or_replay(
        self,
        command: SharedMemoryMutationCommand,
        fingerprints: MemoryFingerprints,
    ) -> BeginMutationResult:
        with self._session_factory() as session:
            existing = session.scalar(
                select(MemoryMutation).where(
                    MemoryMutation.idempotency_key == command.idempotency_key
                )
            )
            if existing is not None:
                return self._replay(existing, fingerprints)

            mutation = MemoryMutation(
                mutation_id=str(uuid4()),
                idempotency_key=command.idempotency_key,
                payload_fingerprint=fingerprints.payload_fingerprint,
                fact_key=fingerprints.fact_key,
                category=command.category.value,
                fact_kind=command.fact_kind.value,
                requested_at=datetime.now(UTC),
                source_type=command.source_type,
                source_id=command.source_id,
                operator_id=command.operator_id,
                expected_version=command.expected_version,
                incoming_confidence=command.confidence,
                incoming_timestamp=command.incoming_at,
                human_confirmed=command.human_confirmed,
                reason=command.reason,
                targets_json=sorted(target.value for target in command.targets),
                proposed_fact_json=command.to_dict(),
                status="PENDING",
                vector_status=(
                    ProjectionStatus.PENDING.value
                    if MemoryTarget.VECTOR in command.targets
                    else ProjectionStatus.NOT_REQUIRED.value
                ),
                graph_status=(
                    ProjectionStatus.PENDING.value
                    if MemoryTarget.GRAPH in command.targets
                    else ProjectionStatus.NOT_REQUIRED.value
                ),
            )
            session.add(mutation)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(MemoryMutation).where(
                        MemoryMutation.idempotency_key == command.idempotency_key
                    )
                )
                if existing is None:
                    raise
                return self._replay(existing, fingerprints)
            return BeginMutationResult(
                mutation_id=mutation.mutation_id,
                replayed=False,
                payload_fingerprint=mutation.payload_fingerprint,
            )

    @staticmethod
    def _replay(
        existing: MemoryMutation,
        fingerprints: MemoryFingerprints,
    ) -> BeginMutationResult:
        if existing.payload_fingerprint != fingerprints.payload_fingerprint:
            raise MemoryIdempotencyConflict(existing.idempotency_key)
        return BeginMutationResult(
            mutation_id=existing.mutation_id,
            replayed=True,
            payload_fingerprint=existing.payload_fingerprint,
        )

    def append_evidence(
        self,
        mutation_id: str,
        command: SharedMemoryMutationCommand,
        fingerprints: MemoryFingerprints,
    ) -> bool:
        with self._session_factory() as session:
            duplicate = session.scalar(
                select(MemoryEvidence.id).where(
                    MemoryEvidence.mutation_id == mutation_id,
                    MemoryEvidence.evidence_fingerprint == fingerprints.evidence_fingerprint,
                )
            )
            if duplicate is not None:
                return False
            session.add(
                MemoryEvidence(
                    evidence_id=str(uuid4()),
                    mutation_id=mutation_id,
                    evidence_fingerprint=fingerprints.evidence_fingerprint,
                    source_type=command.source_type,
                    source_id=command.source_id,
                    evidence_text=command.evidence_text,
                    evidence_ref=command.evidence_ref,
                    observed_at=command.evidence_observed_at or command.incoming_at,
                    confidence=command.confidence,
                    safe_summary=(command.evidence_text or command.evidence_ref or "")[:512],
                    created_at=datetime.now(UTC),
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return False
            return True

    def append_attempt(
        self,
        mutation_id: str,
        *,
        result: str,
        vector_before: str = ProjectionStatus.PENDING.value,
        vector_after: str = ProjectionStatus.PENDING.value,
        graph_before: str = ProjectionStatus.PENDING.value,
        graph_after: str = ProjectionStatus.PENDING.value,
        error_code: str | None = None,
        error_summary: str | None = None,
    ) -> int:
        with self._session_factory() as session:
            previous = session.scalar(
                select(func.max(MemoryMutationAttempt.attempt_no)).where(
                    MemoryMutationAttempt.mutation_id == mutation_id
                )
            )
            attempt_no = (previous or 0) + 1
            now = datetime.now(UTC)
            session.add(
                MemoryMutationAttempt(
                    attempt_id=str(uuid4()),
                    mutation_id=mutation_id,
                    attempt_no=attempt_no,
                    started_at=now,
                    completed_at=now,
                    vector_before=vector_before,
                    vector_after=vector_after,
                    graph_before=graph_before,
                    graph_after=graph_after,
                    result=result,
                    error_code=error_code,
                    error_summary=error_summary[:512] if error_summary else None,
                )
            )
            session.commit()
            return attempt_no

    def record_decision(self, mutation_id: str, decision: MemoryDecision) -> StoredMutation:
        with self._session_factory() as session:
            mutation = self._required_mutation(session, mutation_id)
            mutation.decision = decision.decision.value
            mutation.reason_code = decision.reason_code
            mutation.before_version = decision.before_version
            mutation.after_version = decision.after_version
            if decision.decision.value == "NOOP":
                mutation.status = MutationStatus.APPLIED.value
                mutation.completed_at = datetime.now(UTC)
            elif decision.decision.value == "REJECT":
                mutation.status = MutationStatus.REJECTED.value
                mutation.completed_at = datetime.now(UTC)
            elif decision.decision.value == "CONFLICT_REVIEW":
                mutation.status = MutationStatus.CONFLICT.value
                mutation.completed_at = datetime.now(UTC)
            if not decision.requires_projection:
                mutation.vector_status = ProjectionStatus.NOT_REQUIRED.value
                mutation.graph_status = ProjectionStatus.NOT_REQUIRED.value
            session.commit()
            return self._stored(mutation)

    def mark_applying(self, mutation_id: str) -> StoredMutation:
        return self._set_mutation_fields(mutation_id, status=MutationStatus.APPLYING.value)

    def update_projection_status(
        self,
        mutation_id: str,
        target: MemoryTarget,
        status: str,
    ) -> StoredMutation:
        ProjectionStatus(status)
        field = "vector_status" if target is MemoryTarget.VECTOR else "graph_status"
        return self._set_mutation_fields(mutation_id, **{field: status})

    def mark_partial(
        self,
        mutation_id: str,
        *,
        error_code: str,
        error_summary: str,
    ) -> StoredMutation:
        return self._set_mutation_fields(
            mutation_id,
            status=MutationStatus.PARTIAL.value,
            error_code=error_code[:64],
            error_summary=error_summary[:512],
        )

    def finalize_canonical(
        self,
        mutation_id: str,
        command: SharedMemoryMutationCommand,
        fingerprints: MemoryFingerprints,
        decision: MemoryDecision,
        *,
        now: datetime,
    ) -> SharedMemoryFact:
        with self._session_factory() as session:
            mutation = self._required_mutation(session, mutation_id)
            fact = session.scalar(
                select(SharedMemoryFact).where(SharedMemoryFact.fact_key == fingerprints.fact_key)
            )
            if (
                fact is not None
                and fact.last_mutation_id == mutation_id
                and fact.version == decision.after_version
            ):
                mutation.status = MutationStatus.FINALIZING.value
                session.commit()
                return fact

            actual_version = fact.version if fact else None
            if actual_version != decision.before_version:
                raise MemoryVersionConflict(
                    fingerprints.fact_key,
                    decision.before_version,
                    actual_version,
                )

            if fact is None:
                fact = SharedMemoryFact(
                    fact_id=str(uuid4()),
                    fact_key=fingerprints.fact_key,
                    category=command.category.value,
                    fact_kind=command.fact_kind.value,
                    subject_type=command.subject_type,
                    subject_id=command.subject_id,
                    predicate=command.predicate,
                    object_type=command.object_type,
                    object_id=command.object_id,
                    value_json=command.value_json,
                    content_fingerprint=fingerprints.content_fingerprint,
                    version=decision.after_version or 1,
                    confidence=command.confidence,
                    status=decision.proposed_status.value,
                    expires_at=command.expires_at,
                    vector_memory_id=command.vector_memory_id,
                    graph_fact_key=command.graph_fact_key,
                    last_mutation_id=mutation_id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(fact)
            else:
                fact.category = command.category.value
                fact.fact_kind = command.fact_kind.value
                fact.subject_type = command.subject_type
                fact.subject_id = command.subject_id
                fact.predicate = command.predicate
                fact.object_type = command.object_type
                fact.object_id = command.object_id
                fact.value_json = command.value_json
                fact.content_fingerprint = fingerprints.content_fingerprint
                fact.confidence = command.confidence
                fact.status = decision.proposed_status.value
                fact.expires_at = command.expires_at
                fact.vector_memory_id = command.vector_memory_id
                fact.graph_fact_key = command.graph_fact_key
                fact.last_mutation_id = mutation_id
                fact.updated_at = now

            mutation.status = MutationStatus.FINALIZING.value
            mutation.error_code = None
            mutation.error_summary = None
            session.flush()
            session.query(MemoryEvidence).filter(
                MemoryEvidence.mutation_id == mutation_id,
                MemoryEvidence.fact_id.is_(None),
            ).update({MemoryEvidence.fact_id: fact.fact_id}, synchronize_session=False)
            try:
                session.commit()
            except StaleDataError as error:
                session.rollback()
                raise MemoryVersionConflict(
                    fingerprints.fact_key,
                    decision.before_version,
                    None,
                ) from error
            return fact

    def create_pending_review(
        self,
        mutation_id: str,
        command: SharedMemoryMutationCommand,
        fingerprints: MemoryFingerprints,
        *,
        now: datetime,
    ) -> SharedMemoryFact:
        with self._session_factory() as session:
            existing = session.scalar(
                select(SharedMemoryFact).where(SharedMemoryFact.fact_key == fingerprints.fact_key)
            )
            if existing is not None:
                return existing
            fact = SharedMemoryFact(
                fact_id=str(uuid4()),
                fact_key=fingerprints.fact_key,
                category=command.category.value,
                fact_kind=command.fact_kind.value,
                subject_type=command.subject_type,
                subject_id=command.subject_id,
                predicate=command.predicate,
                object_type=command.object_type,
                object_id=command.object_id,
                value_json=command.value_json,
                content_fingerprint=fingerprints.content_fingerprint,
                version=1,
                confidence=command.confidence,
                status=MemoryFactStatus.PENDING_REVIEW.value,
                expires_at=command.expires_at,
                vector_memory_id=command.vector_memory_id,
                graph_fact_key=command.graph_fact_key,
                last_mutation_id=mutation_id,
                created_at=now,
                updated_at=now,
            )
            session.add(fact)
            session.flush()
            session.query(MemoryEvidence).filter(
                MemoryEvidence.mutation_id == mutation_id,
                MemoryEvidence.fact_id.is_(None),
            ).update({MemoryEvidence.fact_id: fact.fact_id}, synchronize_session=False)
            session.commit()
            return fact

    def mark_applied(self, mutation_id: str, *, now: datetime) -> StoredMutation:
        with self._session_factory() as session:
            mutation = self._required_mutation(session, mutation_id)
            allowed = {ProjectionStatus.NOT_REQUIRED.value, ProjectionStatus.ACTIVE.value}
            if mutation.vector_status not in allowed or mutation.graph_status not in allowed:
                raise MemoryProjectionIncomplete(mutation_id)
            fact = session.scalar(
                select(SharedMemoryFact).where(SharedMemoryFact.fact_key == mutation.fact_key)
            )
            if fact is None or fact.version != mutation.after_version:
                raise MemoryProjectionIncomplete(mutation_id)
            mutation.status = MutationStatus.APPLIED.value
            mutation.completed_at = now
            mutation.error_code = None
            mutation.error_summary = None
            session.commit()
            return self._stored(mutation)

    def get_mutation(self, mutation_id: str) -> StoredMutation:
        with self._session_factory() as session:
            return self._stored(self._required_mutation(session, mutation_id))

    def get_fact_detail(self, fact_key: str, *, history_limit: int = 20) -> dict[str, object]:
        if not 1 <= history_limit <= 100:
            raise ValueError("history_limit must be between 1 and 100")
        with self._session_factory() as session:
            fact = session.scalar(
                select(SharedMemoryFact).where(SharedMemoryFact.fact_key == fact_key)
            )
            if fact is None:
                raise LookupError(fact_key)
            mutations = session.scalars(
                select(MemoryMutation)
                .where(MemoryMutation.fact_key == fact_key)
                .order_by(MemoryMutation.created_at.desc())
                .limit(history_limit)
            ).all()
            evidence = session.scalars(
                select(MemoryEvidence)
                .where(MemoryEvidence.fact_id == fact.fact_id)
                .order_by(MemoryEvidence.created_at.desc())
                .limit(history_limit)
            ).all()
            return {
                "fact_key": fact.fact_key,
                "category": fact.category,
                "fact_kind": fact.fact_kind,
                "subject_type": fact.subject_type,
                "subject_id": fact.subject_id,
                "predicate": fact.predicate,
                "object_type": fact.object_type,
                "object_id": fact.object_id,
                "version": fact.version,
                "confidence": format(fact.confidence, "f"),
                "status": fact.status,
                "expires_at": fact.expires_at.isoformat() if fact.expires_at else None,
                "vector_memory_id": fact.vector_memory_id,
                "graph_fact_key": fact.graph_fact_key,
                "last_mutation_id": fact.last_mutation_id,
                "updated_at": fact.updated_at.isoformat(),
                "value_json": dict(fact.value_json),
                "projection_incomplete": any(
                    mutation.status in {"PARTIAL", "FINALIZING"} for mutation in mutations
                ),
                "mutations": [
                    {
                        "mutation_id": mutation.mutation_id,
                        "decision": mutation.decision,
                        "status": mutation.status,
                        "before_version": mutation.before_version,
                        "after_version": mutation.after_version,
                        "vector_status": mutation.vector_status,
                        "graph_status": mutation.graph_status,
                        "source_type": mutation.source_type,
                        "source_id": mutation.source_id,
                        "operator_id": mutation.operator_id,
                        "incoming_confidence": format(mutation.incoming_confidence, "f"),
                        "reason_code": mutation.reason_code,
                        "error_code": mutation.error_code,
                        "error_summary": mutation.error_summary,
                        "created_at": mutation.created_at.isoformat(),
                        "completed_at": mutation.completed_at.isoformat() if mutation.completed_at else None,
                    }
                    for mutation in mutations
                ],
                "evidence": [
                    {
                        "evidence_id": item.evidence_id,
                        "source_type": item.source_type,
                        "source_id": item.source_id,
                        "summary": item.safe_summary,
                        "observed_at": item.observed_at.isoformat(),
                        "confidence": format(item.confidence, "f"),
                    }
                    for item in evidence
                ],
            }

    def get_active_fact(self, fact_key: str, *, now: datetime) -> SharedMemoryFactSnapshot | None:
        with self._session_factory() as session:
            fact = session.scalar(
                select(SharedMemoryFact).where(
                    SharedMemoryFact.fact_key == fact_key,
                    SharedMemoryFact.status == "ACTIVE",
                    or_(SharedMemoryFact.expires_at.is_(None), SharedMemoryFact.expires_at > now),
                )
            )
            if fact is None:
                return None
            evidence = frozenset(
                session.scalars(
                    select(MemoryEvidence.evidence_fingerprint).where(
                        MemoryEvidence.fact_id == fact.fact_id
                    )
                ).all()
            )
            return SharedMemoryFactSnapshot(
                fact_key=fact.fact_key,
                version=fact.version,
                content_fingerprint=fact.content_fingerprint,
                confidence=fact.confidence,
                status=MemoryFactStatus(fact.status),
                updated_at=self._as_utc(fact.updated_at),
                expires_at=self._as_utc(fact.expires_at),
                evidence_fingerprints=evidence,
            )

    def load_fact(self, fact_key: str) -> SharedMemoryFactSnapshot | None:
        with self._session_factory() as session:
            fact = session.scalar(
                select(SharedMemoryFact).where(SharedMemoryFact.fact_key == fact_key)
            )
            if fact is None:
                return None
            evidence = frozenset(
                session.scalars(
                    select(MemoryEvidence.evidence_fingerprint).where(
                        MemoryEvidence.fact_id == fact.fact_id
                    )
                ).all()
            )
            return SharedMemoryFactSnapshot(
                fact_key=fact.fact_key,
                version=fact.version,
                content_fingerprint=fact.content_fingerprint,
                confidence=fact.confidence,
                status=MemoryFactStatus(fact.status),
                updated_at=self._as_utc(fact.updated_at),
                expires_at=self._as_utc(fact.expires_at),
                evidence_fingerprints=evidence,
            )

    def _set_mutation_fields(self, mutation_id: str, **fields: object) -> StoredMutation:
        with self._session_factory() as session:
            mutation = self._required_mutation(session, mutation_id)
            for name, value in fields.items():
                setattr(mutation, name, value)
            session.commit()
            return self._stored(mutation)

    @staticmethod
    def _required_mutation(session: Session, mutation_id: str) -> MemoryMutation:
        mutation = session.scalar(
            select(MemoryMutation).where(MemoryMutation.mutation_id == mutation_id)
        )
        if mutation is None:
            raise LookupError(f"Unknown memory mutation: {mutation_id}")
        return mutation

    @staticmethod
    def _stored(mutation: MemoryMutation) -> StoredMutation:
        return StoredMutation(
            mutation_id=mutation.mutation_id,
            fact_key=mutation.fact_key,
            decision=mutation.decision,
            reason_code=mutation.reason_code,
            status=mutation.status,
            before_version=mutation.before_version,
            after_version=mutation.after_version,
            vector_status=mutation.vector_status,
            graph_status=mutation.graph_status,
            error_code=mutation.error_code,
            error_summary=mutation.error_summary,
            proposed_fact_json=dict(mutation.proposed_fact_json),
        )

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
