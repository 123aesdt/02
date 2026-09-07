from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.security.dependencies import get_current_principal
from app.security.errors import SecurityHttpError
from app.security.models import AuthenticatedPrincipal, AuthMethod
from app.security.permissions import ROLE_PERMISSION_MATRIX, Permission, Role
from app.security.rate_limit import RateLimitDecision
from app.security.ws_ticket import ConsumedWsTicket


class AllowAllRateLimitAdmission:
    async def check(self, principal, operation) -> RateLimitDecision:
        return RateLimitDecision(True, 1_000_000, 0, 1)


TEST_WS_TICKET = "t" * 43


class AllowAllWsTicketService:
    def __init__(self, *, can_review: bool) -> None:
        self._can_review = can_review

    async def consume(self, ticket, **scope) -> ConsumedWsTicket:
        now = datetime.now(UTC)
        return ConsumedWsTicket(
            subject_id="test-admin",
            target_type=scope["target_type"],
            target_id=scope["target_id"],
            required_permission=scope["required_permission"],
            issued_at=now,
            expires_at=now + timedelta(minutes=1),
            can_review=self._can_review,
        )


class NoOpSecurityAuditRecorder:
    def record(self, request, **fields) -> None:
        return None


def ws_ticket_url(path: str) -> str:
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}ticket={TEST_WS_TICKET}"


def principal_for(role: Role = Role.ADMIN) -> AuthenticatedPrincipal:
    now = datetime.now(UTC)
    return AuthenticatedPrincipal(
        subject_id=f"test-{role.value.lower()}",
        display_name=f"Test {role.value.title()}",
        roles=frozenset({role}),
        permissions=ROLE_PERMISSION_MATRIX[role],
        auth_method=AuthMethod.DEVELOPMENT_JWT,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
        jti=f"test-{role.value.lower()}-session",
    )


def authorize_app(app: FastAPI, role: Role = Role.ADMIN) -> FastAPI:
    principal = principal_for(role)
    app.dependency_overrides[get_current_principal] = lambda: principal
    app.state.rate_limit_admission = AllowAllRateLimitAdmission()
    app.state.ws_ticket_service = AllowAllWsTicketService(can_review=principal.can(Permission.DISPATCH_REVIEW))
    app.state.security_audit_recorder = NoOpSecurityAuditRecorder()

    @app.exception_handler(SecurityHttpError)
    async def security_error_handler(_request, error: SecurityHttpError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"code": error.code, "message": error.message},
            headers=error.headers,
        )

    return app
