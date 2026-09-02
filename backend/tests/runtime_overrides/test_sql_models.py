from sqlalchemy import JSON, Numeric

from app.models.runtime_override import RuntimeOverride, RuntimeOverrideAttempt


def test_runtime_override_schema_has_json_timing_and_unique_guards() -> None:
    assert isinstance(RuntimeOverride.__table__.c.old_value_json.type, JSON)
    assert isinstance(RuntimeOverride.__table__.c.new_value_json.type, JSON)
    assert isinstance(RuntimeOverrideAttempt.__table__.c.total_ms.type, Numeric)
    assert RuntimeOverrideAttempt.__table__.c.total_ms.type.precision == 12
    assert RuntimeOverrideAttempt.__table__.c.total_ms.type.scale == 3

    unique_sets = {
        tuple(column.name for column in constraint.columns)
        for model in (RuntimeOverride, RuntimeOverrideAttempt)
        for constraint in model.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("override_id",) in unique_sets
    assert ("idempotency_key",) in unique_sets
    assert ("override_id", "attempt_no") in unique_sets


def test_runtime_override_tables_are_part_of_alembic_metadata() -> None:
    assert RuntimeOverride.__tablename__ == "runtime_overrides"
    assert RuntimeOverrideAttempt.__tablename__ == "runtime_override_attempts"
