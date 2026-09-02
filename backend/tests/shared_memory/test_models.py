from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.shared_memory.models import (
    MemoryCategory,
    MemoryFactKind,
    MemoryTarget,
    MutationDecision,
    MutationStatus,
    ProjectionStatus,
    SharedMemoryMutationCommand,
)

NOW = datetime(2026, 8, 27, 1, 0, tzinfo=UTC)


def command(**changes: object) -> SharedMemoryMutationCommand:
    values: dict[str, object] = {
        "idempotency_key": "idem-vehicle-status-8",
        "category": MemoryCategory.DISPATCH,
        "fact_kind": MemoryFactKind.ATTRIBUTE,
        "subject_type": "Vehicle",
        "subject_id": "vehicle-a",
        "predicate": "STATUS",
        "value_json": {"status": "Broken"},
        "confidence": Decimal("0.9000"),
        "incoming_at": NOW,
        "source_type": "operator",
        "source_id": "ops-console",
        "operator_id": "operator-1",
        "human_confirmed": True,
        "reason": "confirmed inspection",
        "evidence_text": "vehicle cannot start",
        "evidence_observed_at": NOW,
        "targets": frozenset({MemoryTarget.GRAPH}),
    }
    values.update(changes)
    return SharedMemoryMutationCommand(**values)


def test_command_is_frozen_and_json_serializable() -> None:
    item = command()

    with pytest.raises(FrozenInstanceError):
        item.reason = "changed"  # type: ignore[misc]

    payload = item.to_dict()
    assert payload["category"] == "DispatchMemory"
    assert payload["confidence"] == "0.9000"
    assert payload["incoming_at"] == "2026-08-27T01:00:00+00:00"
    assert payload["targets"] == ["GRAPH"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("confidence", Decimal("1.0001"), "confidence"),
        ("incoming_at", datetime(2026, 8, 27, 1, 0), "timezone-aware"),
        ("evidence_observed_at", datetime(2026, 8, 27, 1, 0), "timezone-aware"),
        ("reason", "r" * 513, "reason"),
        ("evidence_text", "e" * 2001, "evidence_text"),
        ("evidence_ref", "https://example.test/" + "x" * 500, "evidence_ref"),
        ("value_json", {"reading": float("nan")}, "finite"),
    ],
)
def test_command_rejects_invalid_bounds(field: str, value: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        command(**{field: value})


def test_command_rejects_value_json_over_16_kib() -> None:
    with pytest.raises(ValueError, match="16 KiB"):
        command(value_json={"note": "界" * 6000})


def test_command_requires_evidence_text_or_reference() -> None:
    with pytest.raises(ValueError, match="evidence"):
        command(evidence_text=None, evidence_ref=None)


def test_relationship_requires_object_identity() -> None:
    with pytest.raises(ValueError, match="object_type"):
        command(fact_kind=MemoryFactKind.RELATIONSHIP)


def test_lifecycle_enums_include_visibility_protocol() -> None:
    assert MutationStatus.FINALIZING.value == "FINALIZING"
    assert {status.value for status in ProjectionStatus} == {
        "NOT_REQUIRED",
        "PENDING",
        "STAGED",
        "ACTIVE",
        "RETIRED",
        "FAILED",
    }
    assert {decision.value for decision in MutationDecision} == {
        "CREATE",
        "MERGE",
        "REPLACE",
        "REJECT",
        "CONFLICT_REVIEW",
        "NOOP",
    }


def test_non_dispatch_category_remains_representable_at_domain_boundary() -> None:
    assert command(category=MemoryCategory.CHAT).category is MemoryCategory.CHAT

