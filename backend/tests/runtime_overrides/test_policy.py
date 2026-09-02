from dataclasses import replace

import pytest

from app.runtime_overrides.models import RuntimeOverrideDecision
from app.runtime_overrides.policy import RuntimeOverridePolicy
from app.runtime_threads.models import RuntimeThreadStatus

from .factories import normal_state, stable_environment_thread
from .test_models import command

POLICY = RuntimeOverridePolicy()


def test_runtime_override_field_allowlist() -> None:
    result = POLICY.evaluate(command(field="decision"), stable_environment_thread(), normal_state())

    assert (result.decision, result.error_code) == (
        RuntimeOverrideDecision.REJECTED,
        "OVERRIDE_FIELD_NOT_ALLOWED",
    )


@pytest.mark.parametrize("new_value", ["BROKEN", "UNAVAILABLE", "MAINTENANCE"])
def test_runtime_override_value_validation(new_value: str) -> None:
    result = POLICY.evaluate(command(new_value=new_value), stable_environment_thread(), normal_state())

    assert result.allowed is True


def test_runtime_override_recovery_to_normal_is_rejected() -> None:
    result = POLICY.evaluate(
        command(old_value="BROKEN", new_value="NORMAL"),
        stable_environment_thread(),
        normal_state(vehicle_status="BROKEN"),
    )

    assert (result.decision, result.error_code) == (
        RuntimeOverrideDecision.REJECTED,
        "OVERRIDE_VALUE_INVALID",
    )


def test_runtime_override_old_value_precondition() -> None:
    result = POLICY.evaluate(command(old_value="NORMAL"), stable_environment_thread(), normal_state(vehicle_status="MAINTENANCE"))

    assert result.error_code == "RUNTIME_STATE_PRECONDITION_FAILED"


def test_runtime_override_terminal_rejected() -> None:
    thread = replace(stable_environment_thread(), status=RuntimeThreadStatus.TERMINAL)

    assert POLICY.evaluate(command(), thread, normal_state()).error_code == "THREAD_TERMINAL"


def test_runtime_override_not_stable_rejected() -> None:
    thread = replace(stable_environment_thread(), status=RuntimeThreadStatus.RUNNING)

    assert POLICY.evaluate(command(), thread, normal_state()).error_code == "THREAD_NOT_STABLE"


def test_runtime_override_wrong_boundary_is_rejected() -> None:
    thread = replace(stable_environment_thread(), current_node="capacity", next_node="routing")

    result = POLICY.evaluate(command(), thread, normal_state())

    assert (result.decision, result.error_code) == (
        RuntimeOverrideDecision.NEEDS_DIFFERENT_BOUNDARY,
        "THREAD_NOT_STABLE",
    )


def test_runtime_override_entity_must_match_canonical_state() -> None:
    result = POLICY.evaluate(command(entity_id="vehicle-999"), stable_environment_thread(), normal_state())

    assert result.error_code == "RUNTIME_STATE_PRECONDITION_FAILED"
