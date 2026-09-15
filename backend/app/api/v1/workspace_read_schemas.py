from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class OverviewResponse(WorkspaceResponse):
    orders: int
    anomalies: int
    reviews: int
    runtime_threads: int
    provenance: Literal["LIVE", "DEMO", "MIXED"]


class OrderListItemResponse(WorkspaceResponse):
    row_id: int
    order_no: str
    status: str
    driver_id: str | None
    vehicle_id: str | None
    route_id: str | None
    origin: str
    destination: str
    created_at: datetime
    updated_at: datetime
    anomaly_count: int
    latest_task_id: str | None


class AnomalyListItemResponse(WorkspaceResponse):
    row_id: int
    anomaly_no: str
    order_no: str | None
    driver_id: str | None
    vehicle_id: str | None
    route_id: str | None
    latest_task_id: str | None
    anomaly_type: str
    risk: str
    description: str
    status: str
    reported_at: datetime


class ReviewListItemResponse(WorkspaceResponse):
    row_id: int
    task_id: str
    order_no: str | None
    risk: str | None
    reason: str | None
    vehicle_id: str | None
    original_route_id: str | None
    suggested_route_id: str | None
    status: str
    created_at: datetime
    ai_analysis_reason: str | None
    ai_recommended_action: str | None
    ai_analysis_mode: str | None
    issue_subtype: str | None


class MyTaskListItemResponse(WorkspaceResponse):
    row_id: int
    task_id: str
    order_no: str | None
    risk: str | None
    description: str | None
    vehicle_id: str | None
    original_route_id: str | None
    suggested_route_id: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    origin: str | None
    destination: str | None
    publication_status: str
    published_at: datetime | None
    route_instruction: str | None
    can_report_anomaly: bool


class MyTaskSummaryResponse(WorkspaceResponse):
    total: int
    ready: int
    waiting: int
    active: int
    ended: int


class RuntimeThreadListItemResponse(WorkspaceResponse):
    row_id: int
    thread_id: str
    task_id: str
    status: str
    current_node: str | None
    next_node: str | None
    state_version: int
    checkpoint_count: int
    worker_consumer: str | None
    terminal_at: datetime | None
    updated_at: datetime


class VectorMemoryListItemResponse(WorkspaceResponse):
    memory_id: str | None
    driver_id: str | None
    route_id: str | None
    anomaly_type: str | None
    historical_resolution: str | None
    created_at: datetime | None
    projection_status: str | None


class OrderPageResponse(WorkspaceResponse):
    items: list[OrderListItemResponse]
    total: int
    next_cursor: str | None
    provenance: Literal["LIVE", "DEMO", "MIXED"]


class AnomalyPageResponse(WorkspaceResponse):
    items: list[AnomalyListItemResponse]
    total: int
    next_cursor: str | None
    provenance: Literal["LIVE", "DEMO", "MIXED"]


class ReviewPageResponse(WorkspaceResponse):
    items: list[ReviewListItemResponse]
    total: int
    next_cursor: str | None
    provenance: Literal["LIVE", "DEMO", "MIXED"]


class MyTaskPageResponse(WorkspaceResponse):
    items: list[MyTaskListItemResponse]
    summary: MyTaskSummaryResponse
    total: int
    next_cursor: str | None
    provenance: Literal["LIVE", "DEMO", "MIXED"]


class RuntimeThreadPageResponse(WorkspaceResponse):
    items: list[RuntimeThreadListItemResponse]
    total: int
    next_cursor: str | None
    provenance: Literal["LIVE", "DEMO", "MIXED"]


class VectorMemoryPageResponse(WorkspaceResponse):
    items: list[VectorMemoryListItemResponse]
    total: int
    next_cursor: str | None
    vector_dimension: int | None
    provenance: Literal["LIVE", "DEMO", "MIXED"]
