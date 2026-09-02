from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse

from app.api.v1.review_decision_schemas import ReviewDecisionRequest, ReviewDecisionResponse
from app.reviews.service import (
    ReviewAlreadyDecided,
    ReviewDecisionService,
    ReviewDispatchMissing,
    ReviewNotFound,
    ReviewReasonRequired,
    ReviewVersionConflict,
)
from app.security.audit import SecurityAuditEventType, SecurityAuditStatus
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission
from app.security.security_audit import SecurityAuditUnavailable

router = APIRouter(prefix="/api/v1/reviews", tags=["review-decisions"])


def get_service(request: Request) -> ReviewDecisionService:
    return request.app.state.review_decision_service


ServiceDependency = Annotated[ReviewDecisionService, Depends(get_service)]
ReviewPrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.DISPATCH_REVIEW))]


@router.post("/{task_id}/decision", response_model=ReviewDecisionResponse)
def decide_review(
    payload: ReviewDecisionRequest,
    service: ServiceDependency,
    principal: ReviewPrincipal,
    request: Request,
    task_id: Annotated[str, Path(min_length=1, max_length=36)],
) -> ReviewDecisionResponse | JSONResponse:
    try:
        result = service.decide(task_id, payload.decision, payload.reason, principal)
    except ReviewNotFound:
        return _error(404, "REVIEW_NOT_FOUND", "没有找到需要复核的任务。")
    except ReviewAlreadyDecided:
        return _error(409, "REVIEW_ALREADY_DECIDED", "该任务已由其他人员处理，请刷新列表。")
    except ReviewDispatchMissing:
        return _error(409, "REVIEW_DISPATCH_MISSING", "该任务缺少可复核的调度方案，无法处理。")
    except ReviewVersionConflict:
        return _error(409, "DISPATCH_VERSION_CONFLICT", "调度方案已发生变化，请刷新后重新确认。")
    except ReviewReasonRequired:
        return _error(422, "REVIEW_REASON_REQUIRED", "拒绝时必须填写至少 2 个字符的原因。")
    recorder = getattr(request.app.state, "security_audit_recorder", None)
    if recorder is not None:
        try:
            recorder.record(
                request,
                event_type=SecurityAuditEventType.REVIEW_DECISION,
                status=SecurityAuditStatus.ALLOWED,
                reason_code="REVIEW_APPROVED" if payload.decision.value == "APPROVE" else "REVIEW_REJECTED",
                principal=principal,
                permission=Permission.DISPATCH_REVIEW,
            )
        except SecurityAuditUnavailable:
            pass
    return ReviewDecisionResponse.model_validate(result, from_attributes=True)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code, "message": message})
