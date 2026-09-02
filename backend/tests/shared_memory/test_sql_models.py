from decimal import Decimal

from sqlalchemy import JSON, Numeric

from app.models.shared_memory import (
    MemoryEvidence,
    MemoryMutation,
    MemoryMutationAttempt,
    SharedMemoryFact,
)
from tests.shared_memory.factories import fact_row


def test_shared_memory_fact_uses_real_optimistic_lock() -> None:
    assert SharedMemoryFact.__mapper__.version_id_col is SharedMemoryFact.__table__.c.version


def test_control_plane_schema_has_json_numeric_and_unique_guards() -> None:
    assert isinstance(SharedMemoryFact.__table__.c.value_json.type, JSON)
    assert isinstance(SharedMemoryFact.__table__.c.confidence.type, Numeric)
    assert SharedMemoryFact.__table__.c.confidence.type.precision == 5
    assert SharedMemoryFact.__table__.c.confidence.type.scale == 4

    unique_sets = {
        tuple(column.name for column in constraint.columns)
        for model in (SharedMemoryFact, MemoryMutation, MemoryEvidence, MemoryMutationAttempt)
        for constraint in model.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("fact_key",) in unique_sets
    assert ("idempotency_key",) in unique_sets
    assert ("mutation_id", "evidence_fingerprint") in unique_sets
    assert ("mutation_id", "attempt_no") in unique_sets


def test_confidence_round_trip_is_decimal(sqlite_factory) -> None:
    with sqlite_factory() as session:
        row = fact_row(confidence=Decimal("0.9000"))
        session.add(row)
        session.commit()
        session.refresh(row)

        assert row.confidence == Decimal("0.9000")
