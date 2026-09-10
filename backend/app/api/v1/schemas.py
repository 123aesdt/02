from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class _StrictEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FleetScoreComponentsResponse(_StrictEvidenceResponse):
    eta_penalty: str | None = None
    distance_penalty: str | None = None
    load_penalty: str | None = None
    road_risk_penalty: str | None = None
    same_station_bonus: str | None = None
    cargo_exact_match_bonus: str | None = None


class RouteScoreComponentsResponse(_StrictEvidenceResponse):
    normalized_minutes: str | None = None
    normalized_distance: str | None = None
    normalized_risk: str | None = None
    time_penalty: str | None = None
    distance_penalty: str | None = None
    risk_penalty: str | None = None


class PathResponse(_StrictEvidenceResponse):
    objective: str
    node_ids: list[str]
    edge_ids: list[str]
    distance_km: str
    estimated_minutes: int
    risk_cost: str
    visited_node_count: int
    scoring_formula: str | None = None


class VehicleCandidateResponse(_StrictEvidenceResponse):
    vehicle_id: str
    driver_id: str | None = None
    vehicle_status: str | None = None
    driver_status: str | None = None
    remaining_capacity_kg: str | None = None
    gross_weight_tons: str | None = None
    cargo_capability: str | None = None
    pickup_route: PathResponse | None = None
    pickup_distance_km: str | None = None
    pickup_eta_minutes: int | None = None
    score: str | None = None
    score_components: FleetScoreComponentsResponse | None = None
    scoring_formula: str | None = None
    eligible: bool | None = None
    exclusion_reasons: list[str] = Field(default_factory=list)


class VehicleAllocationResponse(_StrictEvidenceResponse):
    original_vehicle_id: str | None
    target_vehicle_id: str | None
    target_driver_id: str | None
    vehicle_reassigned: bool
    candidate_vehicles: list[VehicleCandidateResponse] = Field(default_factory=list)
    pickup_route: PathResponse | None = None
    scoring_formula: str


class RoadNodeResponse(_StrictEvidenceResponse):
    node_id: str
    name: str
    x_km: str
    y_km: str
    node_type: str


class RoadEdgeResponse(_StrictEvidenceResponse):
    edge_id: str
    name: str
    from_node_id: str
    to_node_id: str
    distance_km: str
    base_minutes: int
    road_level: str
    risk_level: str
    status: str
    congestion_factor: str
    weight_limit_tons: str
    bidirectional: bool
    version: int


class RouteCandidateResponse(_StrictEvidenceResponse):
    route_id: str
    route_name: str
    objective: str
    node_ids: list[str]
    edge_ids: list[str]
    distance_km: str
    estimated_minutes: int
    risk_level: str
    risk_cost: str
    visited_node_count: int
    available: bool
    reason: str | None
    score: str
    score_components: RouteScoreComponentsResponse | None = None
    scoring_formula: str
    algorithm_version: str | None = None
    road_network_version: int | None = None


class RoutePlanResponse(_StrictEvidenceResponse):
    original_path: PathResponse | None = None
    recommended_path: PathResponse | None = None
    candidate_routes: list[RouteCandidateResponse] = Field(default_factory=list)
    blocked_edge_ids: list[str] = Field(default_factory=list)
    distance_delta_km: str | None = None
    eta_delta_minutes: int | None = None
    visited_node_count: int | None = None
    routing_status: str | None = None
    algorithm: str
    road_network_version: int | None = None
    network_nodes: list[RoadNodeResponse]
    network_edges: list[RoadEdgeResponse]


class TaskResultResponse(BaseModel):
    task_id: str
    order_id: int
    ready: bool
    status: str
    anomaly_type: str | None = None
    dispatch: DispatchResultResponse | None = None
    audit: AuditResultResponse | None = None
    publication: PublicationResultResponse | None = None
    vehicle_allocation: VehicleAllocationResponse | None = None
    route_plan: RoutePlanResponse | None = None


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
