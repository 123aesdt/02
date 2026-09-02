from datetime import UTC, datetime

import pytest

from app.security.audit import SecurityAuditEvent, SecurityAuditEventType, SecurityAuditStatus
from app.security.permissions import Permission


def test_security_audit_denied() -> None:
    event = SecurityAuditEvent.denied(
        event_id="event-1",
        event_type=SecurityAuditEventType.AUTHORIZATION_DENIED,
        subject_id="dispatcher-1",
        permission=Permission.RUNTIME_OVERRIDE,
        route_template="/api/v1/runtime/threads/{thread_id}/overrides",
        reason_code="MISSING_PERMISSION",
        request_id="request-1",
        remote_ip="192.0.2.10",
        created_at=datetime(2026, 8, 28, 9, tzinfo=UTC),
    )

    assert event.status is SecurityAuditStatus.DENIED
    assert event.permission is Permission.RUNTIME_OVERRIDE
    assert event.remote_ip == "192.0.2.10"
    assert event.to_record() == {
        "event_id": "event-1",
        "subject_id": "dispatcher-1",
        "event_type": "AUTHORIZATION_DENIED",
        "permission": "runtime:override",
        "route_template": "/api/v1/runtime/threads/{thread_id}/overrides",
        "status": "DENIED",
        "reason_code": "MISSING_PERMISSION",
        "request_id": "request-1",
        "remote_ip": "192.0.2.10",
        "created_at": datetime(2026, 8, 28, 9, tzinfo=UTC),
    }


@pytest.mark.parametrize("field", ["raw_token", "authorization", "cookie", "request_body", "password", "api_key"])
def test_security_audit_schema_cannot_accept_sensitive_payload(field: str) -> None:
    values = {
        "event_id": "event-1",
        "event_type": SecurityAuditEventType.TOKEN_INVALID,
        "subject_id": None,
        "permission": None,
        "route_template": "/api/v1/auth/me",
        "status": SecurityAuditStatus.DENIED,
        "reason_code": "TOKEN_INVALID",
        "request_id": "request-1",
        "remote_ip": None,
        "created_at": datetime.now(UTC),
        field: "secret-value",
    }

    with pytest.raises(TypeError):
        SecurityAuditEvent(**values)


def test_security_audit_rejects_raw_route_query() -> None:
    with pytest.raises(ValueError, match="route_template"):
        SecurityAuditEvent.denied(
            event_id="event-1",
            event_type=SecurityAuditEventType.AUTHENTICATION_FAILED,
            subject_id=None,
            permission=None,
            route_template="/api/v1/auth/me?token=secret",
            reason_code="TOKEN_INVALID",
            request_id="request-1",
            remote_ip=None,
            created_at=datetime.now(UTC),
        )


def test_security_audit_rejects_untrusted_remote_ip() -> None:
    with pytest.raises(ValueError, match="remote_ip"):
        SecurityAuditEvent.denied(
            event_id="event-1",
            event_type=SecurityAuditEventType.AUTHENTICATION_FAILED,
            subject_id=None,
            permission=None,
            route_template="/api/v1/auth/me",
            reason_code="TOKEN_INVALID",
            request_id="request-1",
            remote_ip="not-an-ip",
            created_at=datetime.now(UTC),
        )
