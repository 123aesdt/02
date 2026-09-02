from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class Page[T]:
    items: tuple[T, ...]
    total: int
    next_cursor: str | None
    provenance: Literal["LIVE", "DEMO", "MIXED"] = "LIVE"


@dataclass(frozen=True)
class OrderListItem:
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


@dataclass(frozen=True)
class AnomalyListItem:
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


@dataclass(frozen=True)
class ReviewListItem:
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
    ai_analysis_reason: str | None = None
    ai_recommended_action: str | None = None
    ai_analysis_mode: str | None = None
    issue_subtype: str | None = None


@dataclass(frozen=True)
class MyTaskListItem:
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
    origin: str | None = None
    destination: str | None = None
    publication_status: str = "PENDING"
    published_at: datetime | None = None
    route_instruction: str | None = None


@dataclass(frozen=True)
class MyTaskSummary:
    total: int
    ready: int
    waiting: int
    active: int
    ended: int


@dataclass(frozen=True)
class MyTaskPage:
    items: tuple[MyTaskListItem, ...]
    summary: MyTaskSummary
    total: int
    next_cursor: str | None
    provenance: Literal["LIVE", "DEMO", "MIXED"] = "LIVE"


@dataclass(frozen=True)
class TeamTaskListItem:
    row_id: int
    task_id: str
    assignee_subject_id: str
    assignee_display_name: str
    order_no: str | None
    risk: str | None
    description: str | None
    vehicle_id: str | None
    original_route_id: str | None
    suggested_route_id: str | None
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class TeamTaskSummary:
    total: int
    ready: int
    waiting: int
    active: int
    ended: int


@dataclass(frozen=True)
class TeamMemberTaskSummary:
    subject_id: str
    display_name: str
    total: int
    ready: int
    waiting: int
    active: int
    ended: int


@dataclass(frozen=True)
class TeamTaskPage:
    items: tuple[TeamTaskListItem, ...]
    summary: TeamTaskSummary
    members: tuple[TeamMemberTaskSummary, ...]
    total: int
    next_cursor: str | None
    provenance: Literal["LIVE", "DEMO", "MIXED"] = "LIVE"


@dataclass(frozen=True)
class RuntimeThreadListItem:
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


@dataclass(frozen=True)
class DomainCounts:
    orders: int
    anomalies: int
    reviews: int
    runtime_threads: int
    provenance: Literal["LIVE", "DEMO", "MIXED"]


@dataclass(frozen=True)
class VectorMemoryListItem:
    memory_id: str | None
    driver_id: str | None
    route_id: str | None
    anomaly_type: str | None
    historical_resolution: str | None
    created_at: datetime | None
    projection_status: str | None


@dataclass(frozen=True)
class VectorMemoryPage:
    items: tuple[VectorMemoryListItem, ...]
    total: int
    next_cursor: str | None
    vector_dimension: int | None
    provenance: Literal["LIVE", "DEMO", "MIXED"] = "LIVE"
