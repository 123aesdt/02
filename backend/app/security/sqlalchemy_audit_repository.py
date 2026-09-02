from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.security_audit import SecurityAuditRecord
from app.security.audit import SecurityAuditEvent


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class SqlAlchemySecurityAuditRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def append(self, event: SecurityAuditEvent) -> None:
        with self._session_factory() as session, session.begin():
            session.add(SecurityAuditRecord(**event.to_record()))

    def list_recent(self, *, limit: int) -> list[SecurityAuditEvent]:
        if not 1 <= limit <= 500:
            raise ValueError("security audit limit must be between 1 and 500")
        with self._session_factory() as session:
            rows = session.scalars(select(SecurityAuditRecord).order_by(SecurityAuditRecord.created_at.desc()).limit(limit)).all()
        return [SecurityAuditEvent(**{**self._record(row), "created_at": _aware(row.created_at)}) for row in rows]

    def delete_before(self, cutoff: datetime, *, limit: int) -> int:
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("security audit retention cutoff must be timezone-aware")
        if not 1 <= limit <= 10_000:
            raise ValueError("security audit deletion limit must be between 1 and 10000")
        with self._session_factory() as session, session.begin():
            ids = session.scalars(
                select(SecurityAuditRecord.id)
                .where(SecurityAuditRecord.created_at < cutoff)
                .order_by(SecurityAuditRecord.created_at)
                .limit(limit)
            ).all()
            if not ids:
                return 0
            session.execute(delete(SecurityAuditRecord).where(SecurityAuditRecord.id.in_(ids)))
            return len(ids)

    @staticmethod
    def _record(row: SecurityAuditRecord) -> dict[str, object]:
        return {
            "event_id": row.event_id,
            "subject_id": row.subject_id,
            "event_type": row.event_type,
            "permission": row.permission,
            "route_template": row.route_template,
            "status": row.status,
            "reason_code": row.reason_code,
            "request_id": row.request_id,
            "remote_ip": row.remote_ip,
        }

