from typing import Protocol

from app.anomaly_reports.models import (
    AnomalyReportCommand,
    DispatchTaskIdentity,
    PersistedAnomalyReport,
    SourceTaskContext,
)
from app.api.v1.schemas import CreateDispatchTaskRequest


class AnomalyReportRepository(Protocol):
    def get_source_task(self, task_id: str) -> SourceTaskContext | None: ...

    def get_report_by_key(self, idempotency_key: str) -> PersistedAnomalyReport | None: ...

    def create_report(
        self,
        command: AnomalyReportCommand,
        source: SourceTaskContext,
        principal_subject_id: str,
    ) -> PersistedAnomalyReport: ...

    def get_dispatch_task_by_key(self, idempotency_key: str) -> DispatchTaskIdentity | None: ...


class DispatchSubmissionService(Protocol):
    async def submit(
        self,
        request: CreateDispatchTaskRequest,
        *,
        assignee_subject_id: str,
    ) -> dict[str, object]: ...
