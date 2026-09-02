from dataclasses import dataclass
from typing import TypedDict


class AuditChecks(TypedDict):
    route_consistency: bool
    memory_consistency: bool
    fallback_consistency: bool
    dispatch_execution: bool


@dataclass(frozen=True)
class AuditResult:
    audit_status: str
    passed: bool
    reason: str
    checks: AuditChecks
    dispatch_id: int | None
    requires_manual_review: bool
    audit_record_id: int | None
