from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.anomaly_reports import (
    AnomalyReportCommand,
    AnomalyReportService,
    ReportIdempotencyConflict,
    ReportQueueUnavailable,
    ReportSourceForbidden,
    SourceContextIncomplete,
    SourceTaskEnded,
    SourceTaskNotFound,
)
from app.api.v1.anomaly_report_schemas import AnomalyReportRequest, AnomalyReportResponse
from app.security.audit import SecurityAuditEventType, SecurityAuditStatus
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission
from app.security.rate_limit import OperationClass, RateLimitDecision, require_rate_limit
from app.security.security_audit import SecurityAuditUnavailable

router = APIRouter(prefix="/api/v1/anomaly-reports", tags=["anomaly-reports"])


def get_service(request: Request) -> AnomalyReportService:
    return request.app.state.anomaly_report_service


ServiceDependency = Annotated[AnomalyReportService, Depends(get_service)]
ReportPrincipal = Annotated[
    AuthenticatedPrincipal,
    Depends(require_permission(Permission.ANOMALIES_REPORT)),
]
ReportRateLimit = Annotated[
    RateLimitDecision,
    Depends(require_rate_limit(OperationClass.DISPATCH_SUBMIT)),
]


@router.post("", response_model=AnomalyReportResponse, status_code=status.HTTP_202_ACCEPTED)
async def report_anomaly(
    payload: AnomalyReportRequest,
    service: ServiceDependency,
    principal: ReportPrincipal,
    _rate_limit: ReportRateLimit,
    request: Request,
) -> AnomalyReportResponse | JSONResponse:
    command = AnomalyReportCommand(
        source_task_id=payload.source_task_id,
        anomaly_type=payload.anomaly_type.value,
        description=payload.description,
        location_text=payload.location_text,
        reported_vehicle_status=payload.reported_vehicle_status.value,
        severity=payload.severity.value,
        idempotency_key=payload.idempotency_key,
        incident_node_id=payload.incident_node_id,
        affected_edge_id=payload.affected_edge_id,
    )
    try:
        result = await service.submit(command, principal_subject_id=principal.subject_id)
    except ReportSourceForbidden:
        _audit(request, principal, SecurityAuditStatus.DENIED, "REPORT_SOURCE_FORBIDDEN")
        return _error(403, "REPORT_SOURCE_FORBIDDEN", "只能为分配给本人的任务上报问题。")
    except SourceTaskNotFound:
        _audit(request, principal, SecurityAuditStatus.DENIED, "SOURCE_TASK_NOT_FOUND")
        return _error(404, "SOURCE_TASK_NOT_FOUND", "没有找到原配送任务。")
    except SourceTaskEnded:
        _audit(request, principal, SecurityAuditStatus.DENIED, "SOURCE_TASK_ENDED")
        return _error(409, "SOURCE_TASK_ENDED", "该配送任务已经结束，不能继续上报问题。")
    except ReportIdempotencyConflict:
        _audit(request, principal, SecurityAuditStatus.DENIED, "IDEMPOTENCY_CONFLICT")
        return _error(409, "IDEMPOTENCY_CONFLICT", "该幂等键已经用于另一份问题内容。")
    except SourceContextIncomplete:
        _audit(request, principal, SecurityAuditStatus.ERROR, "SOURCE_CONTEXT_INCOMPLETE")
        return _error(422, "SOURCE_CONTEXT_INCOMPLETE", "原任务缺少司机、车辆或路线信息，请联系调度员。")
    except ReportQueueUnavailable as error:
        _audit(request, principal, SecurityAuditStatus.ERROR, "REPORT_QUEUE_UNAVAILABLE")
        return JSONResponse(
            status_code=503,
            content={
                "code": "REPORT_QUEUE_UNAVAILABLE",
                "message": "问题已保存，但 AI 调度暂未启动。请使用相同内容重试。",
                "anomaly_id": error.anomaly_id,
                "anomaly_no": error.anomaly_no,
                "task_id": error.task_id,
                "retryable": True,
            },
        )

    _audit(request, principal, SecurityAuditStatus.ALLOWED, "ANOMALY_REPORT_ACCEPTED")
    return AnomalyReportResponse(
        anomaly_id=result.anomaly_id,
        anomaly_no=result.anomaly_no,
        task_id=result.task_id,
        status=result.status,
        accepted=True,
        duplicate=result.duplicate,
        message="问题已上报，AI 调度已启动。",
    )


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code, "message": message})


def _audit(
    request: Request,
    principal: AuthenticatedPrincipal,
    audit_status: SecurityAuditStatus,
    reason_code: str,
) -> None:
    recorder = getattr(request.app.state, "security_audit_recorder", None)
    if recorder is None:
        return
    try:
        recorder.record(
            request,
            event_type=SecurityAuditEventType.ANOMALY_REPORT,
            status=audit_status,
            reason_code=reason_code,
            principal=principal,
            permission=Permission.ANOMALIES_REPORT,
        )
    except SecurityAuditUnavailable:
        return
