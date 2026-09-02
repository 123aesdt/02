from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.v1.runtime_thread_schemas import RuntimeThreadDetailResponse, RuntimeThreadHistoryResponse
from app.runtime_threads.service import RuntimeThreadAuthorizationError, RuntimeThreadNotFoundError, RuntimeThreadStateUnavailableError, ThreadStateService
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission

router = APIRouter(prefix="/api/v1/runtime/threads", tags=["runtime-threads"])


def get_service(request: Request) -> ThreadStateService:
    return request.app.state.runtime_thread_service


ServiceDependency = Annotated[ThreadStateService, Depends(get_service)]
RuntimeReadPrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.RUNTIME_READ))]


@router.get("/by-task/{task_id}", response_model=RuntimeThreadDetailResponse)
async def get_runtime_thread_by_task(task_id: str, service: ServiceDependency, _principal: RuntimeReadPrincipal):
    return await _read(service.get_current_by_task(task_id, _principal))


@router.get("/{thread_id}/history", response_model=RuntimeThreadHistoryResponse)
async def get_runtime_thread_history(
    thread_id: str,
    service: ServiceDependency,
    _principal: RuntimeReadPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return await _read(service.list_history(thread_id, _principal, limit=limit))


@router.get("/{thread_id}", response_model=RuntimeThreadDetailResponse)
async def get_runtime_thread(thread_id: str, service: ServiceDependency, _principal: RuntimeReadPrincipal):
    return await _read(service.get_current_by_thread(thread_id, _principal))


async def _read(operation):
    try:
        return await operation
    except RuntimeThreadAuthorizationError as error:
        raise HTTPException(403, detail={"code": "RUNTIME_THREAD_FORBIDDEN"}) from error
    except RuntimeThreadNotFoundError as error:
        raise HTTPException(404, detail={"code": "RUNTIME_THREAD_NOT_FOUND"}) from error
    except RuntimeThreadStateUnavailableError as error:
        raise HTTPException(503, detail={"code": "RUNTIME_CHECKPOINT_UNAVAILABLE"}) from error
