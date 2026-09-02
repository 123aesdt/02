from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.api.v1.schemas import (
    CreateDispatchTaskRequest,
    CreateDispatchTaskResponse,
    DispatchPublicationResponse,
    TaskResultResponse,
    TaskStatusResponse,
)
from app.publications.service import (
    PublicationDispatchMissing,
    PublicationNotApproved,
    PublicationRouteMissing,
    PublicationTaskNotFound,
)
from app.security.audit import SecurityAuditEventType, SecurityAuditStatus
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission
from app.security.rate_limit import OperationClass, RateLimitDecision, require_rate_limit
from app.security.security_audit import SecurityAuditUnavailable
from app.services.dispatch_task_api_service import (
    AssigneeNotFoundError,
    DispatchTaskApiService,
    IdempotencyConflictError,
    SubmissionQueueError,
    TaskAccessForbiddenError,
    TaskNotFoundError,
)

router = APIRouter(prefix="/api/v1/dispatch-tasks", tags=["dispatch-tasks"])


def get_service(request: Request) -> DispatchTaskApiService:
    return request.app.state.dispatch_task_api_service


def get_publication_service(request: Request):
    return request.app.state.dispatch_publication_service


ServiceDependency = Annotated[DispatchTaskApiService, Depends(get_service)]
DispatchCreatePrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.DISPATCH_CREATE))]
DispatchReadPrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.DISPATCH_READ))]
DispatchPublishPrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.DISPATCH_REVIEW))]
PublicationServiceDependency = Annotated[object, Depends(get_publication_service)]
DispatchSubmitRateLimit = Annotated[
    RateLimitDecision,
    Depends(require_rate_limit(OperationClass.DISPATCH_SUBMIT)),
]


@router.post("", response_model=CreateDispatchTaskResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_dispatch_task(
    payload: CreateDispatchTaskRequest,
    service: ServiceDependency,
    principal: DispatchCreatePrincipal,
    _rate_limit: DispatchSubmitRateLimit,
) -> CreateDispatchTaskResponse | JSONResponse:
    assignee_subject_id = payload.assignee_employee_id or principal.subject_id
    try:
        return CreateDispatchTaskResponse.model_validate(
            await service.submit(payload, assignee_subject_id=assignee_subject_id)
        )
    except AssigneeNotFoundError:
        return JSONResponse(
            status_code=422,
            content={"code": "ASSIGNEE_NOT_FOUND", "message": "请选择一个已启用的配送员工作为接收员工。"},
        )
    except IdempotencyConflictError:
        return JSONResponse(
            status_code=409,
            content={"code": "IDEMPOTENCY_CONFLICT", "message": "The idempotency key is already associated with another task."},
        )
    except SubmissionQueueError:
        return JSONResponse(
            status_code=503,
            content={"code": "QUEUE_UNAVAILABLE", "message": "Dispatch task could not be submitted. Please retry later."},
        )


@router.post("/{task_id}/publish", response_model=DispatchPublicationResponse)
def publish_dispatch_task(
    task_id: str,
    service: PublicationServiceDependency,
    principal: DispatchPublishPrincipal,
    request: Request,
) -> DispatchPublicationResponse | JSONResponse:
    try:
        result = service.publish(task_id, principal)
    except PublicationTaskNotFound:
        return JSONResponse(status_code=404, content={"code": "PUBLICATION_TASK_NOT_FOUND", "message": "没有找到可发布的调度任务。"})
    except PublicationDispatchMissing:
        return JSONResponse(status_code=409, content={"code": "PUBLICATION_DISPATCH_MISSING", "message": "该任务缺少可发布的调度方案。"})
    except PublicationNotApproved:
        return JSONResponse(status_code=409, content={"code": "PUBLICATION_NOT_APPROVED", "message": "调度方案尚未审核通过，不能发布。"})
    except PublicationRouteMissing:
        return JSONResponse(status_code=409, content={"code": "PUBLICATION_ROUTE_MISSING", "message": "调度方案缺少可下发路线。"})
    recorder = getattr(request.app.state, "security_audit_recorder", None)
    if recorder is not None:
        try:
            recorder.record(
                request,
                event_type=SecurityAuditEventType.DISPATCH_PUBLICATION,
                status=SecurityAuditStatus.ALLOWED,
                reason_code="DISPATCH_PUBLISHED",
                principal=principal,
                permission=Permission.DISPATCH_REVIEW,
            )
        except SecurityAuditUnavailable:
            pass
    return DispatchPublicationResponse.model_validate(result)


@router.get("/{task_id}", response_model=TaskStatusResponse)
def get_dispatch_task(task_id: str, service: ServiceDependency, principal: DispatchReadPrincipal) -> TaskStatusResponse | JSONResponse:
    try:
        service.require_read_access(
            task_id,
            subject_id=principal.subject_id,
            can_read_all=principal.can(Permission.DISPATCH_CREATE),
        )
        return TaskStatusResponse.model_validate(service.status(task_id))
    except TaskAccessForbiddenError:
        return JSONResponse(
            status_code=403,
            content={"code": "TASK_ACCESS_FORBIDDEN", "message": "只能查看分配给本人的任务。"},
        )
    except TaskNotFoundError as error:
        raise HTTPException(404, detail={"code": "TASK_NOT_FOUND", "message": "Dispatch task was not found."}) from error


@router.get("/{task_id}/result", response_model=TaskResultResponse, status_code=status.HTTP_200_OK)
def get_dispatch_result(
    task_id: str,
    service: ServiceDependency,
    principal: DispatchReadPrincipal,
) -> TaskResultResponse | JSONResponse:
    try:
        service.require_read_access(
            task_id,
            subject_id=principal.subject_id,
            can_read_all=principal.can(Permission.DISPATCH_CREATE),
        )
        result = service.result(
            task_id,
            include_unpublished=principal.can(Permission.DISPATCH_REVIEW),
        )
    except TaskAccessForbiddenError:
        return JSONResponse(
            status_code=403,
            content={"code": "TASK_ACCESS_FORBIDDEN", "message": "只能查看分配给本人的任务。"},
        )
    except TaskNotFoundError as error:
        raise HTTPException(404, detail={"code": "TASK_NOT_FOUND", "message": "Dispatch task was not found."}) from error
    response = TaskResultResponse.model_validate(result)
    if not response.ready:
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=response.model_dump(mode="json"))
    return response
