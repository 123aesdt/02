from datetime import UTC, datetime
from decimal import Decimal

from app.shared_memory.identity import (
    build_fact_key,
    canonical_json,
    content_fingerprint,
    evidence_fingerprint,
    payload_fingerprint,
)
from app.shared_memory.models import MemoryCategory, MemoryFactKind, MemoryTarget, SharedMemoryMutationCommand

NOW = datetime(2026, 8, 27, 1, 0, tzinfo=UTC)


def command(**changes: object) -> SharedMemoryMutationCommand:
    values: dict[str, object] = {
        "idempotency_key": "idem-vehicle-status-8",
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
        "reason": "confirmed inspection",
        "evidence_text": "vehicle inspected",
        "evidence_observed_at": NOW,
        "targets": frozenset({MemoryTarget.GRAPH}),
    }
    values.update(changes)
    return SharedMemoryMutationCommand(**values)


def test_attribute_fact_key_is_stable_across_value_change() -> None:
    normal = command(value_json={"status": "Normal"})
    broken = command(value_json={"status": "Broken"})

    assert build_fact_key(normal) == build_fact_key(broken)
    assert content_fingerprint(normal) != content_fingerprint(broken)


def test_relationship_fact_key_includes_object_identity() -> None:
    first = command(
        fact_kind=MemoryFactKind.RELATIONSHIP,
        object_type="Route",
        object_id="route-a",
    )
    second = command(
        fact_kind=MemoryFactKind.RELATIONSHIP,
        object_type="Route",
        object_id="route-b",
    )

    assert build_fact_key(first) != build_fact_key(second)


def test_payload_fingerprint_is_order_independent() -> None:
    left = command(value_json={"b": 2, "a": 1})
    right = command(value_json={"a": 1, "b": 2})

    assert payload_fingerprint(left) == payload_fingerprint(right)


def test_payload_fingerprint_excludes_idempotency_key() -> None:
    left = command(idempotency_key="idem-a")
    right = command(idempotency_key="idem-b")

    assert payload_fingerprint(left) == payload_fingerprint(right)


def test_evidence_fingerprint_changes_with_provenance() -> None:
    left = command(source_id="sensor-a")
    right = command(source_id="sensor-b")

    assert evidence_fingerprint(left) != evidence_fingerprint(right)


def test_canonical_json_is_utf8_stable_and_compact() -> None:
    assert canonical_json({"路线": "国道102", "b": 2, "a": 1}) == '{"a":1,"b":2,"路线":"国道102"}'


def test_fact_key_has_stable_sha256_shape() -> None:
    fact_key = build_fact_key(command())

    assert fact_key.startswith("smf_")
    assert len(fact_key) == 68
    assert fact_key[4:].isalnum()

