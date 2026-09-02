import ipaddress
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.security.permissions import Permission


class SecurityAuditEventType(StrEnum):
    SECURITY_ADMISSION = "SECURITY_ADMISSION"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    ANOMALY_REPORT = "ANOMALY_REPORT"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    RUNTIME_OVERRIDE_DENIED = "RUNTIME_OVERRIDE_DENIED"
    MEMORY_MUTATION_DENIED = "MEMORY_MUTATION_DENIED"
    REVIEW_DECISION = "REVIEW_DECISION"
    DISPATCH_PUBLICATION = "DISPATCH_PUBLICATION"
    TOKEN_INVALID = "TOKEN_INVALID"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    WS_TICKET_REJECTED = "WS_TICKET_REJECTED"
    SENSITIVE_DATA_REDACTED = "SENSITIVE_DATA_REDACTED"


class SecurityAuditStatus(StrEnum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    ERROR = "ERROR"


def _text(value: str, name: str, maximum: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    return normalized


@dataclass(frozen=True)
class SecurityAuditEvent:
    event_id: str
    event_type: SecurityAuditEventType
    subject_id: str | None
    permission: Permission | None
    route_template: str
    status: SecurityAuditStatus
    reason_code: str
    request_id: str
    remote_ip: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _text(self.event_id, "event_id", 64))
        object.__setattr__(self, "event_type", SecurityAuditEventType(self.event_type))
        object.__setattr__(self, "status", SecurityAuditStatus(self.status))
        object.__setattr__(self, "permission", Permission(self.permission) if self.permission is not None else None)
        if self.subject_id is not None:
            object.__setattr__(self, "subject_id", _text(self.subject_id, "subject_id", 128))
        route = _text(self.route_template, "route_template", 160)
        if not route.startswith("/") or "?" in route or "#" in route:
            raise ValueError("route_template must be a normalized route without query or fragment")
        object.__setattr__(self, "route_template", route)
        object.__setattr__(self, "reason_code", _text(self.reason_code, "reason_code", 64))
        object.__setattr__(self, "request_id", _text(self.request_id, "request_id", 64))
        if self.remote_ip is not None:
            try:
                normalized_ip = str(ipaddress.ip_address(self.remote_ip))
            except ValueError as error:
                raise ValueError("remote_ip must be a valid IP address") from error
            object.__setattr__(self, "remote_ip", normalized_ip)
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")

    @classmethod
    def denied(
        cls,
        *,
        event_id: str,
        event_type: SecurityAuditEventType,
        subject_id: str | None,
        permission: Permission | None,
        route_template: str,
        reason_code: str,
        request_id: str,
        remote_ip: str | None,
        created_at: datetime,
    ) -> "SecurityAuditEvent":
        return cls(
            event_id=event_id,
            event_type=event_type,
            subject_id=subject_id,
            permission=permission,
            route_template=route_template,
            status=SecurityAuditStatus.DENIED,
            reason_code=reason_code,
            request_id=request_id,
            remote_ip=remote_ip,
            created_at=created_at,
        )

    def to_record(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "subject_id": self.subject_id,
            "event_type": self.event_type.value,
            "permission": self.permission.value if self.permission else None,
            "route_template": self.route_template,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "request_id": self.request_id,
            "remote_ip": self.remote_ip,
            "created_at": self.created_at,
        }
