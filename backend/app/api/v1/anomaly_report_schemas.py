from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AnomalyReportType(StrEnum):
    ROAD_BLOCKED = "ROAD_BLOCKED"
    ROAD_HAZARD = "ROAD_HAZARD"
    VEHICLE_BREAKDOWN = "VEHICLE_BREAKDOWN"
    WEATHER = "WEATHER"
    CARGO = "CARGO"
    CAPACITY = "CAPACITY"
    OTHER = "OTHER"


class ReportedVehicleStatus(StrEnum):
    NORMAL = "NORMAL"
    BROKEN = "BROKEN"
    UNAVAILABLE = "UNAVAILABLE"
    MAINTENANCE = "MAINTENANCE"


class AnomalyReportSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AnomalyReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_task_id: str = Field(min_length=1, max_length=36)
    anomaly_type: AnomalyReportType
    description: str = Field(min_length=5, max_length=2_000)
    location_text: str = Field(min_length=1, max_length=255)
    reported_vehicle_status: ReportedVehicleStatus
    severity: AnomalyReportSeverity
    incident_node_id: str | None = Field(default=None, min_length=1, max_length=64)
    affected_edge_id: str | None = Field(default=None, min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=128)


class AnomalyReportResponse(BaseModel):
    anomaly_id: int
    anomaly_no: str
    task_id: str
    status: str
    accepted: bool
    duplicate: bool
    message: str
