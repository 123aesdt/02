from hashlib import sha256

from app.anomaly_reports.models import AnomalyReportCommand, AnomalyReportResult, PersistedAnomalyReport
from app.anomaly_reports.protocols import AnomalyReportRepository, DispatchSubmissionService
from app.api.v1.schemas import CreateDispatchTaskRequest
from app.services.dispatch_task_api_service import IdempotencyConflictError, SubmissionQueueError

REPORTABLE_GROUPS = frozenset({"READY", "WAITING", "ACTIVE"})


class SourceTaskNotFound(Exception):
    pass


class ReportSourceForbidden(Exception):
    pass


class SourceTaskEnded(Exception):
    pass


class SourceTaskNotReportable(Exception):
    pass


class SourceContextIncomplete(Exception):
    pass


class ReportIdempotencyConflict(Exception):
    pass


class ReportQueueUnavailable(Exception):
    def __init__(self, *, anomaly_id: int, anomaly_no: str, task_id: str) -> None:
        super().__init__("anomaly report queue unavailable")
        self.anomaly_id = anomaly_id
        self.anomaly_no = anomaly_no
        self.task_id = task_id


class AnomalyReportService:
    def __init__(
        self,
        repository: AnomalyReportRepository,
        dispatch_service: DispatchSubmissionService,
    ) -> None:
        self._repository = repository
        self._dispatch_service = dispatch_service

    async def submit(
        self,
        command: AnomalyReportCommand,
        *,
        principal_subject_id: str,
    ) -> AnomalyReportResult:
        normalized = self._normalized(command)
        source = self._repository.get_source_task(normalized.source_task_id)
        if source is None:
            raise SourceTaskNotFound
        if source.assignee_subject_id != principal_subject_id:
            raise ReportSourceForbidden
        if not source.can_report_anomaly:
            raise SourceTaskNotReportable
        if source.task_group not in REPORTABLE_GROUPS:
            raise SourceTaskEnded
        if not source.driver_id or not source.vehicle_id or not source.route_id:
            raise SourceContextIncomplete

        report = self._repository.get_report_by_key(normalized.idempotency_key)
        duplicate_report = report is not None
        if report is not None and not self._same_report(report, normalized, principal_subject_id):
            raise ReportIdempotencyConflict
        if report is None:
            report = self._repository.create_report(normalized, source, principal_subject_id)
            if not self._same_report(report, normalized, principal_subject_id):
                raise ReportIdempotencyConflict

        dispatch_key = self._dispatch_key(normalized.idempotency_key)
        request = CreateDispatchTaskRequest(
            order_id=source.order_id,
            anomaly_id=report.anomaly_id,
            driver_id=source.driver_id,
            vehicle_id=source.vehicle_id,
            route_id=source.route_id,
            anomaly_type=normalized.anomaly_type,
            anomaly_description=normalized.description,
            idempotency_key=dispatch_key,
            vehicle_status=normalized.reported_vehicle_status,
            assignee_employee_id=principal_subject_id,
            incident_node_id=normalized.incident_node_id,
            affected_edge_id=normalized.affected_edge_id,
        )
        try:
            accepted = await self._dispatch_service.submit(
                request,
                assignee_subject_id=principal_subject_id,
            )
        except IdempotencyConflictError as error:
            raise ReportIdempotencyConflict from error
        except SubmissionQueueError as error:
            task = self._repository.get_dispatch_task_by_key(dispatch_key)
            raise ReportQueueUnavailable(
                anomaly_id=report.anomaly_id,
                anomaly_no=report.anomaly_no,
                task_id="" if task is None else task.task_id,
            ) from error

        return AnomalyReportResult(
            anomaly_id=report.anomaly_id,
            anomaly_no=report.anomaly_no,
            task_id=str(accepted["task_id"]),
            status=str(accepted["status"]),
            duplicate=duplicate_report or bool(accepted["duplicate"]),
        )

    @staticmethod
    def _dispatch_key(idempotency_key: str) -> str:
        digest = sha256(idempotency_key.encode("utf-8")).hexdigest()
        return f"anomaly-report:{digest}"

    @staticmethod
    def _normalized(command: AnomalyReportCommand) -> AnomalyReportCommand:
        return AnomalyReportCommand(
            source_task_id=command.source_task_id.strip(),
            anomaly_type=command.anomaly_type.strip().upper(),
            description=command.description.strip(),
            location_text=command.location_text.strip(),
            reported_vehicle_status=command.reported_vehicle_status.strip().upper(),
            severity=command.severity.strip().upper(),
            idempotency_key=command.idempotency_key.strip(),
            incident_node_id=None if command.incident_node_id is None else command.incident_node_id.strip(),
            affected_edge_id=None if command.affected_edge_id is None else command.affected_edge_id.strip(),
        )

    @staticmethod
    def _same_report(
        report: PersistedAnomalyReport,
        command: AnomalyReportCommand,
        principal_subject_id: str,
    ) -> bool:
        return (
            report.source_task_id == command.source_task_id
            and report.anomaly_type == command.anomaly_type
            and report.description == command.description
            and report.location_text == command.location_text
            and report.reported_vehicle_status == command.reported_vehicle_status
            and report.severity == command.severity
            and report.incident_node_id == command.incident_node_id
            and report.affected_edge_id == command.affected_edge_id
            and report.reported_by_subject_id == principal_subject_id
        )
