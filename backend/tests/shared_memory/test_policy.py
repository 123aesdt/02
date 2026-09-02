from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.shared_memory.identity import content_fingerprint, evidence_fingerprint
from app.shared_memory.models import (
    MemoryCategory,
    MemoryFactKind,
    MemoryFactStatus,
    MemoryTarget,
    MutationDecision,
    SharedMemoryMutationCommand,
)
from app.shared_memory.policy import (
    MemoryPolicySettings,
    MemoryVersionConflict,
    SharedMemoryFactSnapshot,
    evaluate_mutation,
)

NOW = datetime(2026, 8, 27, 1, 0, tzinfo=UTC)
SETTINGS = MemoryPolicySettings(
    auto_apply_min_confidence=Decimal("0.7500"),
    lower_confidence_reject_delta=Decimal("0.1500"),
)


def command(**changes: object) -> SharedMemoryMutationCommand:
    values: dict[str, object] = {
        "idempotency_key": "idem-vehicle-status-8",
        "category": MemoryCategory.DISPATCH,
        "fact_kind": MemoryFactKind.ATTRIBUTE,
        "subject_type": "Vehicle",
        "subject_id": "vehicle-a",
        "predicate": "STATUS",
        "value_json": {"status": "Normal"},
        "expected_version": 7,
        "confidence": Decimal("0.9000"),
        "incoming_at": NOW,
        "source_type": "operator",
        "source_id": "ops-console",
        "operator_id": "operator-1",
        "human_confirmed": False,
        "reason": "inspection",
        "evidence_text": "vehicle inspected",
        "evidence_observed_at": NOW,
        "targets": frozenset({MemoryTarget.GRAPH}),
    }
    values.update(changes)
    return SharedMemoryMutationCommand(**values)


def current(incoming: SharedMemoryMutationCommand, **changes: object) -> SharedMemoryFactSnapshot:
    values: dict[str, object] = {
        "fact_key": "smf_current",
        "version": 7,
        "content_fingerprint": content_fingerprint(incoming),
        "confidence": Decimal("0.9000"),
        "status": MemoryFactStatus.ACTIVE,
        "updated_at": NOW - timedelta(minutes=5),
        "expires_at": None,
        "evidence_fingerprints": frozenset({evidence_fingerprint(incoming)}),
    }
    values.update(changes)
    return SharedMemoryFactSnapshot(**values)


def decide(
    incoming: SharedMemoryMutationCommand,
    existing: SharedMemoryFactSnapshot | None,
):
    return evaluate_mutation(existing, incoming, SETTINGS, now=NOW)


def test_memory_create() -> None:
    incoming = command(expected_version=None)
    result = decide(incoming, None)

    assert (result.decision, result.before_version, result.after_version) == (
        MutationDecision.CREATE,
        None,
        1,
    )
    assert result.requires_projection is True


def test_memory_duplicate_noop() -> None:
    incoming = command()
    result = decide(incoming, current(incoming))

    assert result.decision is MutationDecision.NOOP
    assert result.after_version == 7
    assert result.requires_projection is False


def test_memory_merge_evidence() -> None:
    incoming = command(evidence_text="a second inspection")
    existing = current(incoming, evidence_fingerprints=frozenset())

    result = decide(incoming, existing)

    assert result.decision is MutationDecision.MERGE
    assert result.after_version == 8


def test_memory_replace_expired() -> None:
    incoming = command(value_json={"status": "Broken"})
    existing = current(
        incoming,
        content_fingerprint="old-content",
        expires_at=NOW - timedelta(seconds=1),
    )

    assert decide(incoming, existing).decision is MutationDecision.REPLACE


def test_memory_human_confirmed_replace() -> None:
    incoming = command(value_json={"status": "Broken"}, human_confirmed=True)
    existing = current(incoming, content_fingerprint="normal-content")

    result = decide(incoming, existing)

    assert (result.decision, result.after_version) == (MutationDecision.REPLACE, 8)


def test_memory_stale_reject() -> None:
    incoming = command(value_json={"status": "Broken"}, incoming_at=NOW - timedelta(hours=1))
    existing = current(incoming, content_fingerprint="normal-content", updated_at=NOW)

    result = decide(incoming, existing)

    assert (result.decision, result.reason_code) == (MutationDecision.REJECT, "STALE_EVIDENCE")
    assert result.after_version == 7


def test_memory_lower_confidence_reject() -> None:
    incoming = command(value_json={"status": "Broken"}, confidence=Decimal("0.7500"))
    existing = current(incoming, content_fingerprint="normal-content", confidence=Decimal("0.9000"))

    result = decide(incoming, existing)

    assert (result.decision, result.reason_code) == (MutationDecision.REJECT, "LOWER_CONFIDENCE")


def test_memory_conflict_requires_review() -> None:
    incoming = command(value_json={"status": "Broken"}, confidence=Decimal("0.8500"))
    existing = current(incoming, content_fingerprint="normal-content")

    result = decide(incoming, existing)

    assert result.decision is MutationDecision.CONFLICT_REVIEW
    assert result.proposed_status is MemoryFactStatus.CONFLICT


def test_memory_low_confidence_requires_review() -> None:
    incoming = command(expected_version=None, confidence=Decimal("0.7400"))

    result = decide(incoming, None)

    assert result.decision is MutationDecision.CONFLICT_REVIEW
    assert result.proposed_status is MemoryFactStatus.PENDING_REVIEW
    assert result.requires_projection is False


def test_memory_expiry() -> None:
    incoming = command()
    existing = current(incoming, expires_at=NOW)

    assert decide(incoming, existing).decision is MutationDecision.REPLACE


def test_memory_expected_version_conflict_precedes_human_confirmation() -> None:
    incoming = command(value_json={"status": "Broken"}, expected_version=6, human_confirmed=True)

    with pytest.raises(MemoryVersionConflict) as caught:
        decide(incoming, current(incoming, content_fingerprint="normal-content"))

    assert (caught.value.expected_version, caught.value.actual_version) == (6, 7)


def test_same_content_metadata_change_merges() -> None:
    incoming = command(confidence=Decimal("0.9500"))
    existing = current(incoming, confidence=Decimal("0.9000"))

    assert decide(incoming, existing).decision is MutationDecision.MERGE


def test_human_confirmation_can_accept_below_threshold_after_version_check() -> None:
    incoming = command(
        value_json={"status": "Broken"},
        confidence=Decimal("0.4000"),
        human_confirmed=True,
    )
    existing = current(incoming, content_fingerprint="normal-content")

    assert decide(incoming, existing).decision is MutationDecision.REPLACE


def test_snapshot_expiry_is_logical() -> None:
    incoming = command()
    existing = current(incoming, expires_at=NOW + timedelta(seconds=1))

    assert existing.is_expired(NOW) is False
    assert replace(existing, expires_at=NOW).is_expired(NOW) is True

