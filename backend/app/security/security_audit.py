import ipaddress
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Request

from app.observability.context import current_correlation_id, normalize_correlation_id
from app.security.audit import SecurityAuditEvent, SecurityAuditEventType, SecurityAuditStatus
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission


class SecurityAuditUnavailable(Exception):
    """Raised when a required durable security decision cannot be recorded."""


class SecurityAuditRecorder:
    def __init__(self, repository, *, clock=None) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def record(
        self,
        request: Request,
        *,
        event_type: SecurityAuditEventType,
        status: SecurityAuditStatus,
        reason_code: str,
        principal: AuthenticatedPrincipal | None,
        permission: Permission | None,
    ) -> None:
        route = request.scope.get("route")
        route_template = getattr(route, "path", None) or request.url.path
        request_id = current_correlation_id() or normalize_correlation_id(request.headers.get("X-Request-ID"))
        event = SecurityAuditEvent(
            event_id=str(uuid4()),
            event_type=event_type,
            subject_id=principal.subject_id if principal is not None else None,
            permission=permission,
            route_template=route_template,
            status=status,
            reason_code=reason_code,
            request_id=request_id,
            remote_ip=self._remote_ip(request),
            created_at=self._clock(),
        )
        try:
            self._repository.append(event)
        except Exception as error:
            raise SecurityAuditUnavailable from error

    @staticmethod
    def _remote_ip(request: Request) -> str | None:
        if request.client is None:
            return None
        try:
            return str(ipaddress.ip_address(request.client.host))
        except ValueError:
            return None
