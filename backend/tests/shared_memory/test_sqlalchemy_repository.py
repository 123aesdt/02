from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.shared_memory import MemoryEvidence, MemoryMutationAttempt
from app.shared_memory.identity import (
    build_fact_key,
    content_fingerprint,
    evidence_fingerprint,
    payload_fingerprint,
)
from app.shared_memory.models import MemoryCategory, MemoryFactKind, MemoryFactStatus, MemoryTarget, MutationDecision, SharedMemoryMutationCommand
from app.shared_memory.policy import MemoryDecision
from app.shared_memory.protocols import MemoryFingerprints
from app.shared_memory.sqlalchemy_repository import (
    MemoryIdempotencyConflict,
    MemoryProjectionIncomplete,
    SqlAlchemyMemoryControlRepository,
)
from tests.shared_memory.factories import fact_row

NOW = datetime(2026, 8, 27, 1, 0, tzinfo=UTC)


def command(**changes: object) -> SharedMemoryMutationCommand:
    values: dict[str, object] = {
        "idempotency_key": "idem-sql-1",
        "category": MemoryCategory.DISPATCH,
        "fact_kind": MemoryFactKind.ATTRIBUTE,
        "subject_type": "Vehicle",
        "subject_id": "vehicle-a",
        "predicate": "STATUS",
        "value_json": {"status": "Normal"},
        "confidence": Decimal("0.9000"),
        "incoming_at": NOW,
        "source_type": "operator",
        "source_id": "ops-console",
        "operator_id": "operator-1",
        "human_confirmed": True,
        "reason": "inspection",
        "evidence_text": "vehicle inspected",
        "evidence_observed_at": NOW,
        "targets": frozenset({MemoryTarget.GRAPH}),
    }
    values.update(changes)
    return SharedMemoryMutationCommand(**values)


def fingerprints(item: SharedMemoryMutationCommand) -> MemoryFingerprints:
    return MemoryFingerprints(
        fact_key=build_fact_key(item),
        content_fingerprint=content_fingerprint(item),
        payload_fingerprint=payload_fingerprint(item),
        evidence_fingerprint=evidence_fingerprint(item),
    )


def test_memory_idempotent_replay(sqlite_factory) -> None:
    repository = SqlAlchemyMemoryControlRepository(sqlite_factory)
    item = command()

    first = repository.begin_or_replay(item, fingerprints(item))
    second = repository.begin_or_replay(item, fingerprints(item))

    assert second.mutation_id == first.mutation_id
    assert (first.replayed, second.replayed) == (False, True)


def test_idempotency_key_with_different_payload_conflicts(sqlite_factory) -> None:
    repository = SqlAlchemyMemoryControlRepository(sqlite_factory)
    original = command()
    conflicting = command(value_json={"status": "Broken"})
    repository.begin_or_replay(original, fingerprints(original))

    with pytest.raises(MemoryIdempotencyConflict):
        repository.begin_or_replay(conflicting, fingerprints(conflicting))


def test_evidence_is_deduplicated_and_attempts_are_append_only(sqlite_factory) -> None:
    repository = SqlAlchemyMemoryControlRepository(sqlite_factory)
    item = command()
    started = repository.begin_or_replay(item, fingerprints(item))

    assert repository.append_evidence(started.mutation_id, item, fingerprints(item)) is True
    assert repository.append_evidence(started.mutation_id, item, fingerprints(item)) is False
    assert repository.append_attempt(started.mutation_id, result="PARTIAL") == 1
    assert repository.append_attempt(started.mutation_id, result="APPLIED") == 2

    with sqlite_factory() as session:
        assert session.query(MemoryEvidence).count() == 1
        assert session.query(MemoryMutationAttempt).count() == 2


def test_active_fact_query_excludes_logically_expired(sqlite_factory) -> None:
    repository = SqlAlchemyMemoryControlRepository(sqlite_factory)
    with sqlite_factory() as session:
        session.add(fact_row(expires_at=NOW - timedelta(seconds=1)))
        session.commit()

    assert repository.get_active_fact("smf_example", now=NOW) is None


def test_finalize_is_atomic_and_applied_requires_active_projection(sqlite_factory) -> None:
    repository = SqlAlchemyMemoryControlRepository(sqlite_factory)
    item = command()
    hashes = fingerprints(item)
    started = repository.begin_or_replay(item, hashes)
    decision = MemoryDecision(
        decision=MutationDecision.CREATE,
        reason_code="NEW_FACT",
        before_version=None,
        after_version=1,
        proposed_status=MemoryFactStatus.ACTIVE,
        requires_projection=True,
    )
    repository.record_decision(started.mutation_id, decision)
    repository.append_evidence(started.mutation_id, item, hashes)
    repository.mark_applying(started.mutation_id)
    repository.update_projection_status(started.mutation_id, MemoryTarget.GRAPH, "STAGED")

    fact = repository.finalize_canonical(started.mutation_id, item, hashes, decision, now=NOW)

    assert (fact.version, repository.get_mutation(started.mutation_id).status) == (1, "FINALIZING")
    with pytest.raises(MemoryProjectionIncomplete):
        repository.mark_applied(started.mutation_id, now=NOW)

    repository.update_projection_status(started.mutation_id, MemoryTarget.GRAPH, "ACTIVE")
    result = repository.mark_applied(started.mutation_id, now=NOW)
    assert (result.status, result.graph_status) == ("APPLIED", "ACTIVE")
    with sqlite_factory() as session:
        evidence = session.query(MemoryEvidence).one()
        assert evidence.fact_id == fact.fact_id


def test_mark_partial_preserves_safe_store_status_and_error(sqlite_factory) -> None:
    repository = SqlAlchemyMemoryControlRepository(sqlite_factory)
    item = command()
    started = repository.begin_or_replay(item, fingerprints(item))

    repository.update_projection_status(started.mutation_id, MemoryTarget.GRAPH, "FAILED")
    result = repository.mark_partial(
        started.mutation_id,
        error_code="NEO4J_WRITE_FAILED",
        error_summary="graph write unavailable",
    )

    assert (result.status, result.graph_status, result.error_code) == (
        "PARTIAL",
        "FAILED",
        "NEO4J_WRITE_FAILED",
    )


def test_fact_detail_exposes_safe_control_plane_and_mutation_metadata(sqlite_factory) -> None:
    repository = SqlAlchemyMemoryControlRepository(sqlite_factory)
    item = command(vector_memory_id="memory-vehicle-a-status", graph_fact_key="Vehicle:vehicle-a:STATUS")
    hashes = fingerprints(item)
    started = repository.begin_or_replay(item, hashes)
    decision = MemoryDecision(
        decision=MutationDecision.CREATE,
        reason_code="NEW_FACT",
        before_version=None,
        after_version=1,
        proposed_status=MemoryFactStatus.ACTIVE,
        requires_projection=True,
    )
    repository.record_decision(started.mutation_id, decision)
    repository.append_evidence(started.mutation_id, item, hashes)
    repository.mark_applying(started.mutation_id)
    repository.update_projection_status(started.mutation_id, MemoryTarget.GRAPH, "ACTIVE")
    repository.finalize_canonical(started.mutation_id, item, hashes, decision, now=NOW)
    repository.mark_applied(started.mutation_id, now=NOW)

    detail = repository.get_fact_detail(hashes.fact_key)

    assert detail["category"] == "DispatchMemory"
    assert detail["fact_kind"] == "ATTRIBUTE"
    assert detail["subject_type"] == "Vehicle"
    assert detail["subject_id"] == "vehicle-a"
    assert detail["predicate"] == "STATUS"
    assert detail["vector_memory_id"] == "memory-vehicle-a-status"
    assert detail["graph_fact_key"] == "Vehicle:vehicle-a:STATUS"
    assert detail["last_mutation_id"] == started.mutation_id
    assert detail["updated_at"] is not None
    assert detail["mutations"][0]["source_type"] == "operator"
    assert detail["mutations"][0]["source_id"] == "ops-console"
    assert detail["mutations"][0]["operator_id"] == "operator-1"
    assert detail["mutations"][0]["incoming_confidence"] == "0.9000"
    assert detail["mutations"][0]["completed_at"] is not None
