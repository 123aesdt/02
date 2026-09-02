import math
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission
from app.security.rate_limit import OperationClass, RateLimitDecision, require_rate_limit
from app.security.ws_ticket import WsTicketRejected, WsTicketUnavailable
from app.services.dispatch_task_api_service import TaskAccessForbiddenError, TaskNotFoundError

router = APIRouter(prefix="/api/v1/ws-tickets", tags=["websocket-tickets"])


class CreateWsTicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: Literal["task"]
    target_id: str = Field(min_length=1, max_length=128)


class WsTicketResponse(BaseModel):
    ticket: str
    target_type: Literal["task"]
    target_id: str
    expires_at: datetime
    expires_in_seconds: int


WsTicketPrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.DISPATCH_READ))]
WsTicketRateLimit = Annotated[
    RateLimitDecision,
    Depends(require_rate_limit(OperationClass.WS_TICKET)),
]


@router.post("", response_model=WsTicketResponse, status_code=201)
async def issue_ws_ticket(
    payload: CreateWsTicketRequest,
    request: Request,
    principal: WsTicketPrincipal,
    _rate_limit: WsTicketRateLimit,
) -> WsTicketResponse | JSONResponse:
    try:
        request.app.state.dispatch_task_api_service.require_read_access(
            payload.target_id,
            subject_id=principal.subject_id,
            can_read_all=principal.can(Permission.DISPATCH_CREATE),
        )
        request.app.state.dispatch_task_api_service.status(payload.target_id)
    except TaskAccessForbiddenError:
        return JSONResponse(
            status_code=403,
            content={"code": "TASK_ACCESS_FORBIDDEN", "message": "只能订阅分配给本人的任务。"},
        )
    except TaskNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"code": "TASK_NOT_FOUND", "message": "Dispatch task was not found."},
        )
    try:
        issued = await request.app.state.ws_ticket_service.issue(
            principal,
            target_type=payload.target_type,
            target_id=payload.target_id,
            required_permission=Permission.DISPATCH_READ,
        )
    except WsTicketRejected:
        return JSONResponse(
            status_code=403,
            content={"code": "AUTHORIZATION_DENIED", "message": "Permission is required."},
        )
    except WsTicketUnavailable:
        return JSONResponse(
            status_code=503,
            content={
                "code": "SECURITY_CONTROL_UNAVAILABLE",
                "message": "Security admission is temporarily unavailable.",
            },
        )
    return WsTicketResponse(
        ticket=issued.ticket,
        target_type=issued.target_type,
        target_id=issued.target_id,
        expires_at=issued.expires_at,
        expires_in_seconds=max(1, math.ceil((issued.expires_at - datetime.now(UTC)).total_seconds())),
    )
