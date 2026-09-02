from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, Request

from app.security.audit import SecurityAuditEventType, SecurityAuditStatus
from app.security.errors import SecurityHttpError
from app.security.metrics import record_security_metric
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission
from app.security.protocols import AuthenticationError, AuthenticationProviderUnavailable
from app.security.security_audit import SecurityAuditUnavailable

HIGH_RISK_PERMISSIONS = frozenset(
    {
        Permission.DISPATCH_CREATE,
        Permission.MEMORY_MUTATE,
        Permission.RUNTIME_OVERRIDE,
        Permission.SYSTEM_ADMIN,
    }
)


async def get_current_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedPrincipal:
    if authorization is None:
        _audit_authentication_failure(request, "AUTHENTICATION_REQUIRED")
        raise SecurityHttpError(
            401,
            "AUTHENTICATION_REQUIRED",
            "Authentication is required.",
            {"WWW-Authenticate": "Bearer"},
        )
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip() or " " in token.strip():
        _audit_authentication_failure(request, "TOKEN_INVALID")
        raise SecurityHttpError(401, "TOKEN_INVALID", "The access token is invalid.", {"WWW-Authenticate": "Bearer"})
    try:
        return await request.app.state.authentication_provider.authenticate(token.strip())
    except AuthenticationError as error:
        _audit_authentication_failure(request, error.code.value)
        message = "The access token has expired." if error.code.value == "TOKEN_EXPIRED" else "The access token is invalid."
        raise SecurityHttpError(401, error.code.value, message, {"WWW-Authenticate": "Bearer"}) from None
    except AuthenticationProviderUnavailable:
        _audit_authentication_failure(request, "AUTHENTICATION_UNAVAILABLE")
        raise SecurityHttpError(503, "AUTHENTICATION_UNAVAILABLE", "Authentication is temporarily unavailable.") from None


PrincipalDependency = Annotated[AuthenticatedPrincipal, Depends(get_current_principal)]


def require_permission(permission: Permission) -> Callable[..., object]:
    async def dependency(request: Request, principal: PrincipalDependency) -> AuthenticatedPrincipal:
        if not principal.can(permission):
            record_security_metric(
                getattr(request.app.state, "metrics_recorder", None),
                "countyflow_authorization_denied_total",
                reason_code="permission",
                path=request.url.path,
            )
            recorder = getattr(request.app.state, "security_audit_recorder", None)
            if recorder is not None:
                denied_type = {
                    Permission.RUNTIME_OVERRIDE: SecurityAuditEventType.RUNTIME_OVERRIDE_DENIED,
                    Permission.MEMORY_MUTATE: SecurityAuditEventType.MEMORY_MUTATION_DENIED,
                }.get(permission, SecurityAuditEventType.AUTHORIZATION_DENIED)
                try:
                    recorder.record(
                        request,
                        event_type=denied_type,
                        status=SecurityAuditStatus.DENIED,
                        reason_code="AUTHORIZATION_DENIED",
                        principal=principal,
                        permission=permission,
                    )
                except SecurityAuditUnavailable:
                    pass
            raise SecurityHttpError(403, "AUTHORIZATION_DENIED", "Permission is required.")
        if permission in HIGH_RISK_PERMISSIONS:
            recorder = getattr(request.app.state, "security_audit_recorder", None)
            if recorder is None:
                raise SecurityHttpError(
                    503,
                    "SECURITY_CONTROL_UNAVAILABLE",
                    "Security admission is temporarily unavailable.",
                )
            try:
                recorder.record(
                    request,
                    event_type=SecurityAuditEventType.SECURITY_ADMISSION,
                    status=SecurityAuditStatus.ALLOWED,
                    reason_code="AUTHORIZATION_ALLOWED",
                    principal=principal,
                    permission=permission,
                )
            except SecurityAuditUnavailable:
                raise SecurityHttpError(
                    503,
                    "SECURITY_CONTROL_UNAVAILABLE",
                    "Security admission is temporarily unavailable.",
                ) from None
        return principal

    return dependency


def _audit_authentication_failure(request: Request, reason_code: str) -> None:
    metric_reason = {
        "AUTHENTICATION_REQUIRED": "missing",
        "TOKEN_EXPIRED": "expired",
        "AUTHENTICATION_UNAVAILABLE": "provider_unavailable",
    }.get(reason_code, "invalid")
    record_security_metric(
        getattr(request.app.state, "metrics_recorder", None),
        "countyflow_authentication_failures_total",
        reason_code=metric_reason,
        path=request.url.path,
    )
    recorder = getattr(request.app.state, "security_audit_recorder", None)
    if recorder is None:
        return
    event_type = {
        "TOKEN_INVALID": SecurityAuditEventType.TOKEN_INVALID,
        "TOKEN_EXPIRED": SecurityAuditEventType.TOKEN_EXPIRED,
    }.get(reason_code, SecurityAuditEventType.AUTHENTICATION_FAILED)
    try:
        recorder.record(
            request,
            event_type=event_type,
            status=SecurityAuditStatus.DENIED,
            reason_code=reason_code,
            principal=None,
            permission=None,
        )
    except SecurityAuditUnavailable:
        pass
