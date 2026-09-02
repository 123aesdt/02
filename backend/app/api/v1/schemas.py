from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CreateDispatchTaskRequest(BaseModel):
    order_id: int
    anomaly_id: int | None = None
    driver_id: str = Field(min_length=1, max_length=64)
    vehicle_id: str = Field(min_length=1, max_length=64)
    route_id: str = Field(min_length=1, max_length=64)
    anomaly_type: str = Field(min_length=1, max_length=64)
    anomaly_description: str = Field(min_length=1, max_length=2_000)
    idempotency_key: str = Field(min_length=1, max_length=128)
    vehicle_status: Literal["NORMAL", "BROKEN", "UNAVAILABLE", "MAINTENANCE"] = "NORMAL"
    assignee_employee_id: str | None = Field(default=None, min_length=1, max_length=32)


class CreateDispatchTaskResponse(BaseModel):
    task_id: str
    order_id: int
    status: str
    accepted: bool
    duplicate: bool = False
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    order_id: int
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    ready: bool
    requires_manual_review: bool


class DispatchResultResponse(BaseModel):
    dispatch_id: int
    dispatch_no: str
    original_route_id: str | None
    target_route_id: str | None
    status: str
    decision_reason: str | None
    fallback_used: bool
    fallback_reason: str | None
    version: int
    executed: bool


class AuditResultResponse(BaseModel):
    result: str
    reason: str
    dispatch_id: int
    created_at: datetime


class PublicationResultResponse(BaseModel):
    status: str
    route_id: str | None
    route_instruction: str | None
    published_at: datetime | None
    published_by: str | None
    recipient_employee_id: str | None
    recipient_display_name: str | None


class TaskResultResponse(BaseModel):
    task_id: str
    order_id: int
    ready: bool
    status: str
    dispatch: DispatchResultResponse | None = None
    audit: AuditResultResponse | None = None
    publication: PublicationResultResponse | None = None


class DispatchPublicationResponse(BaseModel):
    task_id: str
    dispatch_id: int
    status: str
    route_id: str
    route_instruction: str
    published_at: datetime
    published_by: str
    recipient_employee_id: str
    recipient_display_name: str
    duplicate: bool
