from fastapi import APIRouter, Request, Response

from app.api.v1.auth_schemas import (
    DemoEmployeeResponse,
    DemoEmployeeSessionRequest,
    DevelopmentSessionRequest,
    DevelopmentSessionResponse,
    PrincipalResponse,
)
from app.security.demo_employee_accounts import DemoEmployeeNotFound, DemoEmployeeSessionService
from app.security.dependencies import PrincipalDependency
from app.security.errors import SecurityHttpError
from app.security.permissions import Role
from app.security.protocols import AuthenticationProviderUnavailable

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
DEMO_RUNTIME_PROFILES = frozenset({"local", "docker-dev", "test"})


def _demo_employee_service(request: Request) -> DemoEmployeeSessionService:
    runtime_profile = getattr(request.app.state, "runtime_profile", None)
    service = getattr(request.app.state, "demo_employee_service", None)
    if runtime_profile not in DEMO_RUNTIME_PROFILES or service is None:
        raise SecurityHttpError(404, "NOT_FOUND", "The requested resource was not found.")
    return service


@router.get("/demo-employees", response_model=list[DemoEmployeeResponse])
def demo_employees(request: Request) -> list[DemoEmployeeResponse]:
    return [
        DemoEmployeeResponse(
            employee_id=employee.employee_id,
            display_name=employee.display_name,
            role=employee.role,
        )
        for employee in _demo_employee_service(request).list_accounts()
    ]


@router.post("/demo-session", response_model=DevelopmentSessionResponse)
def demo_session(request: Request, payload: DemoEmployeeSessionRequest) -> DevelopmentSessionResponse:
    try:
        session = _demo_employee_service(request).issue(payload.employee_id)
    except DemoEmployeeNotFound:
        raise SecurityHttpError(404, "NOT_FOUND", "The requested resource was not found.") from None
    return DevelopmentSessionResponse(
        access_token=session.access_token,
        expires_in=session.expires_in,
        principal=PrincipalResponse.model_validate(session.principal.to_public_dict()),
    )


@router.post("/development-session", response_model=DevelopmentSessionResponse)
def development_session(request: Request, payload: DevelopmentSessionRequest | None = None) -> DevelopmentSessionResponse:
    issuer = getattr(request.app.state, "development_session_issuer", None)
    runtime_profile = getattr(request.app.state, "runtime_profile", None)
    if runtime_profile not in {"local", "docker-dev", "test"} or issuer is None:
        raise SecurityHttpError(404, "NOT_FOUND", "The requested resource was not found.")
    session = issuer.issue(payload.role if payload is not None else Role.ADMIN)
    return DevelopmentSessionResponse(
        access_token=session.access_token,
        expires_in=session.expires_in,
        principal=PrincipalResponse.model_validate(session.principal.to_public_dict()),
    )


@router.get("/me", response_model=PrincipalResponse)
def current_principal(principal: PrincipalDependency) -> PrincipalResponse:
    return PrincipalResponse.model_validate(principal.to_public_dict())


@router.post("/logout", status_code=204)
async def logout(request: Request, principal: PrincipalDependency) -> Response:
    try:
        await request.app.state.revocation_store.revoke(principal.jti, principal.expires_at)
    except AuthenticationProviderUnavailable:
        raise SecurityHttpError(503, "AUTHENTICATION_UNAVAILABLE", "Authentication is temporarily unavailable.") from None
    return Response(status_code=204)
