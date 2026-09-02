from datetime import UTC, datetime, timedelta

from app.security.audit import SecurityAuditEvent, SecurityAuditEventType
from app.security.sqlalchemy_audit_repository import SqlAlchemySecurityAuditRepository


def event(event_id: str, created_at: datetime) -> SecurityAuditEvent:
    return SecurityAuditEvent.denied(
        event_id=event_id,
        event_type=SecurityAuditEventType.AUTHENTICATION_FAILED,
        subject_id=None,
        permission=None,
        route_template="/api/v1/auth/me",
        reason_code="TOKEN_INVALID",
        request_id=f"request-{event_id}",
        remote_ip=None,
        created_at=created_at,
    )


def test_repository_appends_and_reads_security_events(sqlite_factory) -> None:
    repository = SqlAlchemySecurityAuditRepository(sqlite_factory)
    now = datetime.now(UTC)

    repository.append(event("event-1", now))

    stored = repository.list_recent(limit=10)
    assert [item.event_id for item in stored] == ["event-1"]
    assert not hasattr(repository, "update")


def test_repository_deletes_only_records_before_retention_cutoff(sqlite_factory) -> None:
    repository = SqlAlchemySecurityAuditRepository(sqlite_factory)
    now = datetime.now(UTC)
    repository.append(event("old", now - timedelta(days=181)))
    repository.append(event("current", now - timedelta(days=179)))

    deleted = repository.delete_before(now - timedelta(days=180), limit=100)

    assert deleted == 1
    assert [item.event_id for item in repository.list_recent(limit=10)] == ["current"]

