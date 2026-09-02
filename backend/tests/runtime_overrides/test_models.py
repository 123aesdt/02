from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from app.runtime_overrides.models import (
    RuntimeOverrideCommand,
    RuntimeOverrideDecision,
    RuntimeOverrideStatus,
    VehicleRuntimeStatus,
)

NOW = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)


def command(**changes: object) -> RuntimeOverrideCommand:
    values: dict[str, object] = {
        "override_id": "00000000-0000-0000-0000-000000000008",
        "idempotency_key": "override-vehicle-8",
        "thread_id": "cf:dispatch:TASK-0123456789abcdef0123456789abcde",
        "entity_type": "Vehicle",
        "entity_id": "vehicle-001",
        "field": "status",
        "old_value": "NORMAL",
        "new_value": "BROKEN",
        "reason": "Confirmed tyre failure",
        "expected_version": 7,
        "expected_next_node": "capacity",
        "operator_id": "operator-1",
        "operator_role": "dispatch-supervisor",
        "operator_permissions": frozenset({"runtime:override"}),
        "requested_at": NOW,
    }
    values.update(changes)
    return RuntimeOverrideCommand(**values)


def test_runtime_override_command_is_immutable_and_serializable() -> None:
    item = command()

    with pytest.raises(FrozenInstanceError):
        item.reason = "changed"  # type: ignore[misc]

    assert item.to_fingerprint_dict() == {
        "entity_id": "vehicle-001",
        "entity_type": "Vehicle",
        "expected_next_node": "capacity",
        "expected_version": 7,
        "field": "status",
        "new_value": "BROKEN",
        "old_value": "NORMAL",
        "reason": "Confirmed tyre failure",
        "thread_id": "cf:dispatch:TASK-0123456789abcdef0123456789abcde",
    }


def test_runtime_override_domain_enums_cover_required_states() -> None:
    assert {item.value for item in VehicleRuntimeStatus} == {
        "NORMAL",
        "BROKEN",
        "UNAVAILABLE",
        "MAINTENANCE",
    }
    assert {item.value for item in RuntimeOverrideStatus} == {
        "PENDING",
        "APPLYING",
        "APPLIED",
        "REJECTED",
        "CONFLICT",
        "PARTIAL",
        "FAILED",
    }
    assert {item.value for item in RuntimeOverrideDecision} == {
        "ALLOWED",
        "REJECTED",
        "NEEDS_DIFFERENT_BOUNDARY",
    }


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"requested_at": datetime(2026, 8, 27, 8, 0)}, "timezone-aware"),
        ({"reason": "x" * 513}, "reason"),
        ({"expected_version": -1}, "expected_version"),
        ({"idempotency_key": ""}, "idempotency_key"),
    ],
)
def test_runtime_override_command_rejects_invalid_bounds(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        command(**changes)
