import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, delete, inspect, select
from sqlalchemy.orm import sessionmaker

from app.models.security_audit import SecurityAuditRecord
from app.security.audit import SecurityAuditEvent, SecurityAuditEventType
from app.security.permissions import Permission
from app.security.sqlalchemy_audit_repository import SqlAlchemySecurityAuditRepository

DATABASE_URL = os.getenv("SECURITY_DATABASE_URL")


def test_real_mysql_security_audit_is_append_only_and_secret_minimized() -> None:
    if not DATABASE_URL:
        pytest.skip("SECURITY_DATABASE_URL is required for real security MySQL integration")
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    sessions = sessionmaker(engine, expire_on_commit=False)
    repository = SqlAlchemySecurityAuditRepository(sessions)
    suffix = uuid.uuid4().hex
    event_id = f"security-real-{suffix}"
    request_id = f"request-{suffix}"
    event = SecurityAuditEvent.denied(
        event_id=event_id,
        event_type=SecurityAuditEventType.AUTHORIZATION_DENIED,
        subject_id="real-mysql-auditor",
        permission=Permission.RUNTIME_OVERRIDE,
        route_template="/api/v1/runtime/threads/{thread_id}/overrides",
        reason_code="AUTHORIZATION_DENIED",
        request_id=request_id,
        remote_ip="127.0.0.1",
        created_at=datetime.now(UTC),
    )

    try:
        repository.append(event)
        with sessions() as session:
            row = session.scalar(select(SecurityAuditRecord).where(SecurityAuditRecord.event_id == event_id))
            assert row is not None
            assert row.subject_id == "real-mysql-auditor"
            assert row.permission == "runtime:override"
            assert row.status == "DENIED"
            assert row.request_id == request_id
        columns = {column["name"] for column in inspect(engine).get_columns("security_audit_events")}
        assert not columns & {"token", "authorization", "cookie", "password", "request_body", "exception"}
        assert not hasattr(repository, "update")
    finally:
        with sessions() as session, session.begin():
            session.execute(delete(SecurityAuditRecord).where(SecurityAuditRecord.event_id == event_id))
        engine.dispose()
