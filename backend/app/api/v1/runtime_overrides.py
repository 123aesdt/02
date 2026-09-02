from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.api.v1.runtime_override_schemas import (
    CreateRuntimeOverrideRequest,
    RuntimeInterventionContextResponse,
    RuntimeOverrideHistoryResponse,
    RuntimeOverrideResponse,
)
from app.runtime_overrides.models import RuntimeOverrideIdempotencyConflict, RuntimeOverrideStatus
from app.runtime_overrides.query_service import RuntimeOverrideQueryError
from app.runtime_overrides.service import RuntimeOverrideServiceError
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission
from app.security.rate_limit import OperationClass, RateLimitDecision, require_rate_limit

router = APIRouter(prefix="/api/v1/runtime", tags=["runtime-overrides"])


def get_service(request: Request):
    return request.app.state.runtime_override_service


def get_query_service(request: Request):
    return request.app.state.runtime_override_query_service


ServiceDependency = Annotated[object, Depends(get_service)]
QueryServiceDependency = Annotated[object, Depends(get_query_service)]
RuntimeOverridePrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.RUNTIME_OVERRIDE))]
RuntimeReadPrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.RUNTIME_READ))]
RuntimeOverrideRateLimit = Annotated[
    RateLimitDecision,
    Depends(require_rate_limit(OperationClass.RUNTIME_OVERRIDE)),
]


@router.post("/threads/{thread_id}/overrides", response_model=RuntimeOverrideResponse)
async def create_runtime_override(
    thread_id: str,
    payload: CreateRuntimeOverrideRequest,
    service: ServiceDependency,
    request: Request,
    principal: RuntimeOverridePrincipal,
    _rate_limit: RuntimeOverrideRateLimit,
):
    try:
        result = await service.apply(thread_id, payload.to_request(), principal=principal)
    except RuntimeOverrideIdempotencyConflict as error:
        return _error(409, error.code)
    except RuntimeOverrideServiceError as error:
        status = 404 if error.code.endswith("NOT_FOUND") else 403 if error.code == "RUNTIME_OVERRIDE_FORBIDDEN" else 409
        return _error(status, error.code)
    if result.status is RuntimeOverrideStatus.APPLIED:
        return RuntimeOverrideResponse.model_validate(result)
    publisher = getattr(request.app.state, "runtime_override_event_publisher", None)
    if publisher is not None:
        try:
            await publisher.publish_status(result)
        except Exception:
            pass
    status_code = {
        "THREAD_TERMINAL": 409,
        "RUNTIME_STATE_VERSION_CONFLICT": 409,
        "RUNTIME_OVERRIDE_BUSY": 409,
        "THREAD_NOT_STABLE": 409,
        "RUNTIME_STATE_PRECONDITION_FAILED": 409,
        "OVERRIDE_FIELD_NOT_ALLOWED": 422,
        "OVERRIDE_VALUE_INVALID": 422,
        "CHECKPOINT_STORE_UNAVAILABLE": 503,
    }.get(result.error_code) or {
        RuntimeOverrideStatus.REJECTED: 422,
        RuntimeOverrideStatus.CONFLICT: 409,
        RuntimeOverrideStatus.PARTIAL: 202,
        RuntimeOverrideStatus.FAILED: 503,
    }.get(result.status, 409)
    return JSONResponse(
        status_code=status_code,
        content=RuntimeOverrideResponse.model_validate(result).model_dump(mode="json"),
    )


@router.get("/threads/{thread_id}/intervention", response_model=RuntimeInterventionContextResponse)
async def get_runtime_intervention_context(
    thread_id: str,
    service: QueryServiceDependency,
    principal: RuntimeReadPrincipal,
):
    try:
        return RuntimeInterventionContextResponse.from_context(await service.get_intervention_context(thread_id, principal))
    except RuntimeOverrideQueryError as error:
        return _query_error(error)


@router.get("/threads/{thread_id}/overrides", response_model=RuntimeOverrideHistoryResponse)
def list_runtime_overrides(
    thread_id: str,
    service: QueryServiceDependency,
    principal: RuntimeReadPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    try:
        return RuntimeOverrideHistoryResponse(
            thread_id=thread_id,
            items=[RuntimeOverrideResponse.model_validate(item) for item in service.list_by_thread(thread_id, principal, limit=limit)],
        )
    except RuntimeOverrideQueryError as error:
        return _query_error(error)


@router.get("/overrides/{override_id}", response_model=RuntimeOverrideResponse)
def get_runtime_override(
    override_id: str,
    service: QueryServiceDependency,
    principal: RuntimeReadPrincipal,
):
    try:
        return RuntimeOverrideResponse.model_validate(service.get(override_id, principal))
    except RuntimeOverrideQueryError as error:
        return _query_error(error)


def _error(status_code: int, code: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code, "message": code})


def _query_error(error: RuntimeOverrideQueryError) -> JSONResponse:
    status = {
        "RUNTIME_THREAD_FORBIDDEN": 403,
        "THREAD_NOT_FOUND": 404,
        "RUNTIME_OVERRIDE_NOT_FOUND": 404,
        "CHECKPOINT_STORE_UNAVAILABLE": 503,
    }.get(error.code, 409)
    return _error(status, error.code)
