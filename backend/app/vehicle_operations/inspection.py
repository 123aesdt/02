from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SafetyInspectionPolicy:
    manual_fault_codes: frozenset[str] = frozenset({"BRAKE_FAILURE", "STEERING_FAILURE", "ACCIDENT", "INJURY"})


class SafetyInspectionService:
    def __init__(self, policy: SafetyInspectionPolicy | None = None) -> None:
        self._policy = policy or SafetyInspectionPolicy()

    def requires_manual(self, *, cargo_type: str, severity: str, fault_code: str) -> bool:
        normalized_fault = fault_code.strip().upper()
        return normalized_fault in self._policy.manual_fault_codes or (cargo_type.strip().upper() == "COLD_CHAIN" and severity.strip().upper() == "CRITICAL")
