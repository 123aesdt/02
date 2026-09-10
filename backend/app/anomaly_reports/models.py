from dataclasses import dataclass


@dataclass(frozen=True)
class AnomalyReportCommand:
    source_task_id: str
    anomaly_type: str
    description: str
    location_text: str
    reported_vehicle_status: str
    severity: str
    idempotency_key: str
    incident_node_id: str | None = None
    affected_edge_id: str | None = None


@dataclass(frozen=True)
class SourceTaskContext:
    task_id: str
    task_group: str | None
    assignee_subject_id: str | None
    order_id: int
    driver_id: str | None
    vehicle_id: str | None
    route_id: str | None


@dataclass(frozen=True)
class PersistedAnomalyReport:
    anomaly_id: int
    anomaly_no: str
    order_id: int
    source_task_id: str
    anomaly_type: str
    description: str
    location_text: str
    reported_vehicle_status: str
    severity: str
    idempotency_key: str
    reported_by_subject_id: str
    incident_node_id: str | None = None
    affected_edge_id: str | None = None


@dataclass(frozen=True)
class DispatchTaskIdentity:
    task_id: str
    status: str


@dataclass(frozen=True)
class AnomalyReportResult:
    anomaly_id: int
    anomaly_no: str
    task_id: str
    status: str
    duplicate: bool
