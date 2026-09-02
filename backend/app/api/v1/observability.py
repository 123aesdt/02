from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.api.v1.observability_schemas import ObservabilitySummaryResponse
from app.observability.service import ObservabilityUnavailable
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission
from app.security.rate_limit import OperationClass, RateLimitDecision, require_rate_limit

router = APIRouter(prefix="/api/v1/observability", tags=["observability"])
Window = Literal["5m", "15m", "1h"]
MonitorPrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.MONITOR_READ))]
ObservabilityRateLimit = Annotated[
    RateLimitDecision,
    Depends(require_rate_limit(OperationClass.OBSERVABILITY_READ)),
]


async def _read(request: Request, window: Window):
    try:
        return ObservabilitySummaryResponse.model_validate(
            await request.app.state.observability_service.summary(window),
            from_attributes=True,
        )
    except ObservabilityUnavailable:
        return JSONResponse(
            status_code=503,
            content={"code": "OBSERVABILITY_UNAVAILABLE", "message": "Live monitoring is temporarily unavailable."},
        )


@router.get("/summary", response_model=ObservabilitySummaryResponse)
async def summary(
    request: Request,
    _principal: MonitorPrincipal,
    _rate_limit: ObservabilityRateLimit,
    window: Annotated[Window, Query()] = "5m",
):
    return await _read(request, window)


@router.get("/agents", response_model=ObservabilitySummaryResponse)
async def agents(
    request: Request,
    _principal: MonitorPrincipal,
    _rate_limit: ObservabilityRateLimit,
    window: Annotated[Window, Query()] = "5m",
):
    return await _read(request, window)


@router.get("/workers", response_model=ObservabilitySummaryResponse)
async def workers(
    request: Request,
    _principal: MonitorPrincipal,
    _rate_limit: ObservabilityRateLimit,
    window: Annotated[Window, Query()] = "5m",
):
    return await _read(request, window)


@router.get("/memory", response_model=ObservabilitySummaryResponse)
async def memory(
    request: Request,
    _principal: MonitorPrincipal,
    _rate_limit: ObservabilityRateLimit,
    window: Annotated[Window, Query()] = "5m",
):
    return await _read(request, window)


@router.get("/runtime", response_model=ObservabilitySummaryResponse)
async def runtime(
    request: Request,
    _principal: MonitorPrincipal,
    _rate_limit: ObservabilityRateLimit,
    window: Annotated[Window, Query()] = "5m",
):
    return await _read(request, window)


@router.get("/dependencies", response_model=ObservabilitySummaryResponse)
async def dependencies(
    request: Request,
    _principal: MonitorPrincipal,
    _rate_limit: ObservabilityRateLimit,
    window: Annotated[Window, Query()] = "5m",
):
    return await _read(request, window)
