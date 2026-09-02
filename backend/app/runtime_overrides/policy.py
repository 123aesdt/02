from collections.abc import Mapping

from app.runtime_overrides.models import (
    OverridePolicyResult,
    RuntimeOverrideCommand,
    RuntimeOverrideDecision,
    VehicleRuntimeStatus,
)
from app.runtime_threads.models import RuntimeThreadSnapshot, RuntimeThreadStatus

ALLOWED_TARGET = ("Vehicle", "status")
ALLOWED_BOUNDARY = ("environment", "capacity")
ALLOWED_TRANSITIONS = {
    (VehicleRuntimeStatus.NORMAL.value, VehicleRuntimeStatus.BROKEN.value),
    (VehicleRuntimeStatus.NORMAL.value, VehicleRuntimeStatus.UNAVAILABLE.value),
    (VehicleRuntimeStatus.NORMAL.value, VehicleRuntimeStatus.MAINTENANCE.value),
}


class RuntimeOverridePolicy:
    def evaluate(
        self,
        command: RuntimeOverrideCommand,
        thread: RuntimeThreadSnapshot,
        state: Mapping[str, object],
    ) -> OverridePolicyResult:
        if thread.status is RuntimeThreadStatus.TERMINAL:
            return OverridePolicyResult(RuntimeOverrideDecision.REJECTED, "THREAD_TERMINAL")
        if thread.status is not RuntimeThreadStatus.STABLE:
            return OverridePolicyResult(RuntimeOverrideDecision.NEEDS_DIFFERENT_BOUNDARY, "THREAD_NOT_STABLE")
        if (command.entity_type, command.field) != ALLOWED_TARGET:
            return OverridePolicyResult(RuntimeOverrideDecision.REJECTED, "OVERRIDE_FIELD_NOT_ALLOWED")
        if (thread.current_node, thread.next_node) != ALLOWED_BOUNDARY:
            return OverridePolicyResult(RuntimeOverrideDecision.NEEDS_DIFFERENT_BOUNDARY, "THREAD_NOT_STABLE")
        if command.expected_next_node is not None and command.expected_next_node != thread.next_node:
            return OverridePolicyResult(RuntimeOverrideDecision.NEEDS_DIFFERENT_BOUNDARY, "RUNTIME_NEXT_NODE_CONFLICT")
        if (command.old_value, command.new_value) not in ALLOWED_TRANSITIONS:
            return OverridePolicyResult(RuntimeOverrideDecision.REJECTED, "OVERRIDE_VALUE_INVALID")
        if state.get("vehicle_id") != command.entity_id:
            return OverridePolicyResult(RuntimeOverrideDecision.REJECTED, "RUNTIME_STATE_PRECONDITION_FAILED")
        if state.get("vehicle_status") != command.old_value:
            return OverridePolicyResult(RuntimeOverrideDecision.REJECTED, "RUNTIME_STATE_PRECONDITION_FAILED")
        return OverridePolicyResult(RuntimeOverrideDecision.ALLOWED)
