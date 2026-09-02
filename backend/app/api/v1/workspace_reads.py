from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.api.v1.workspace_read_schemas import (
    AnomalyPageResponse,
    MyTaskPageResponse,
    OrderPageResponse,
    OverviewResponse,
    ReviewPageResponse,
    RuntimeThreadPageResponse,
    VectorMemoryPageResponse,
)
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission
from app.workspace_reads.service import (
    InvalidVectorMemoryCursor,
    InvalidWorkspaceCursor,
    VectorMemoryReadUnavailable,
    WorkspaceReadService,
    WorkspaceReadUnavailable,
)

router = APIRouter(prefix="/api/v1", tags=["workspace-reads"])


def get_service(request: Request) -> WorkspaceReadService:
    return request.app.state.workspace_read_service


ServiceDependency = Annotated[WorkspaceReadService, Depends(get_service)]
AdminPrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.SYSTEM_ADMIN))]
OrdersPrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.ORDERS_READ))]
AnomaliesPrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.ANOMALIES_READ))]
ReviewPrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.DISPATCH_REVIEW))]
MyTasksPrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.DISPATCH_READ))]
RuntimePrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.RUNTIME_READ))]
MemoryPrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.MEMORY_READ))]

OrderStatusFilter = Literal[
    "OPEN",
    "open",
    "PENDING",
    "RUNNING",
    "PROCESSING",
    "IN_TRANSIT",
    "DELAYED",
    "COMPLETED",
    "APPROVED",
    "FAILED",
    "CANCELLED",
]
AnomalyStatusFilter = Literal[
    "OPEN",
    "PENDING",
    "RUNNING",
    "PROCESSING",
    "REVIEW_REQUIRED",
    "RESOLVED",
    "COMPLETED",
    "DISMISSED",
    "FAILED",
]
RiskFilter = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
RuntimeStatusFilter = Literal["RUNNING", "STABLE", "OVERRIDING", "TERMINAL"]
MyTaskStateFilter = Literal["READY", "WAITING", "ACTIVE", "ENDED"]


@router.get("/workspace/overview", response_model=OverviewResponse)
def get_overview(service: ServiceDependency, _principal: AdminPrincipal) -> OverviewResponse | JSONResponse:
    try:
        return OverviewResponse.model_validate(service.get_overview(), from_attributes=True)
    except WorkspaceReadUnavailable:
        return _workspace_unavailable()


@router.get("/orders", response_model=OrderPageResponse)
def list_orders(
    service: ServiceDependency,
    _principal: OrdersPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=19, pattern=r"^[0-9]+$")] = None,
    query: Annotated[str | None, Query(max_length=128)] = None,
    status: Annotated[OrderStatusFilter | None, Query()] = None,
) -> OrderPageResponse | JSONResponse:
    try:
        return OrderPageResponse.model_validate(
            service.list_orders(limit=limit, cursor=cursor, query=query, status=status), from_attributes=True
        )
    except InvalidWorkspaceCursor as error:
        raise HTTPException(422, detail={"code": "WORKSPACE_CURSOR_INVALID"}) from error
    except WorkspaceReadUnavailable:
        return _workspace_unavailable()


@router.get("/anomalies", response_model=AnomalyPageResponse)
def list_anomalies(
    service: ServiceDependency,
    _principal: AnomaliesPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=19, pattern=r"^[0-9]+$")] = None,
    query: Annotated[str | None, Query(max_length=128)] = None,
    risk: Annotated[RiskFilter | None, Query()] = None,
    status: Annotated[AnomalyStatusFilter | None, Query()] = None,
) -> AnomalyPageResponse | JSONResponse:
    try:
        return AnomalyPageResponse.model_validate(
            service.list_anomalies(limit=limit, cursor=cursor, query=query, risk=risk, status=status), from_attributes=True
        )
    except InvalidWorkspaceCursor as error:
        raise HTTPException(422, detail={"code": "WORKSPACE_CURSOR_INVALID"}) from error
    except WorkspaceReadUnavailable:
        return _workspace_unavailable()


@router.get("/reviews", response_model=ReviewPageResponse)
def list_reviews(
    service: ServiceDependency,
    _principal: ReviewPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=19, pattern=r"^[0-9]+$")] = None,
) -> ReviewPageResponse | JSONResponse:
    try:
        return ReviewPageResponse.model_validate(service.list_reviews(limit=limit, cursor=cursor), from_attributes=True)
    except InvalidWorkspaceCursor as error:
        raise HTTPException(422, detail={"code": "WORKSPACE_CURSOR_INVALID"}) from error
    except WorkspaceReadUnavailable:
        return _workspace_unavailable()


@router.get("/my/tasks", response_model=MyTaskPageResponse)
def list_my_tasks(
    service: ServiceDependency,
    principal: MyTasksPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=19, pattern=r"^[0-9]+$")] = None,
    state: Annotated[MyTaskStateFilter | None, Query()] = None,
) -> MyTaskPageResponse | JSONResponse:
    try:
        return MyTaskPageResponse.model_validate(
            service.list_my_tasks(
                subject_id=principal.subject_id,
                limit=limit,
                cursor=cursor,
                state=state,
            ),
            from_attributes=True,
        )
    except InvalidWorkspaceCursor as error:
        raise HTTPException(422, detail={"code": "WORKSPACE_CURSOR_INVALID"}) from error
    except WorkspaceReadUnavailable:
        return _workspace_unavailable()


@router.get("/runtime/threads", response_model=RuntimeThreadPageResponse)
def list_runtime_threads(
    service: ServiceDependency,
    _principal: RuntimePrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=19, pattern=r"^[0-9]+$")] = None,
    status: Annotated[RuntimeStatusFilter | None, Query()] = None,
) -> RuntimeThreadPageResponse | JSONResponse:
    try:
        return RuntimeThreadPageResponse.model_validate(
            service.list_runtime_threads(limit=limit, cursor=cursor, status=status), from_attributes=True
        )
    except InvalidWorkspaceCursor as error:
        raise HTTPException(422, detail={"code": "WORKSPACE_CURSOR_INVALID"}) from error
    except WorkspaceReadUnavailable:
        return _workspace_unavailable()


@router.get("/memory/records", response_model=VectorMemoryPageResponse)
async def list_vector_memories(
    service: ServiceDependency,
    _principal: MemoryPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> VectorMemoryPageResponse | JSONResponse:
    try:
        result = await service.list_vector_memories(limit=limit, cursor=cursor)
        return VectorMemoryPageResponse.model_validate(result, from_attributes=True)
    except InvalidVectorMemoryCursor as error:
        raise HTTPException(422, detail={"code": "VECTOR_MEMORY_CURSOR_INVALID"}) from error
    except VectorMemoryReadUnavailable:
        return JSONResponse(
            status_code=503,
            content={"code": "VECTOR_MEMORY_UNAVAILABLE", "message": "Vector memory is temporarily unavailable."},
        )


def _workspace_unavailable() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"code": "WORKSPACE_READ_UNAVAILABLE", "message": "Workspace data is temporarily unavailable."},
    )
