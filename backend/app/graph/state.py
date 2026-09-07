from typing import Literal, NotRequired, TypedDict

VehicleRuntimeStatus = Literal["NORMAL", "BROKEN", "UNAVAILABLE", "MAINTENANCE"]


class MemoryRecallState(TypedDict):
    memory_id: str
    similarity_score: float
    driver_id: str
    route_id: str
    anomaly_type: str
    historical_resolution: str
    metadata: dict[str, object]


class GraphEntityState(TypedDict):
    entity_type: str
    entity_id: str
    display_name: str
    properties: dict[str, object]


class GraphFactState(TypedDict):
    source: GraphEntityState
    relation_type: str
    target: GraphEntityState
    confidence: float
    source_type: str
    evidence: str | None
    version: int
    timestamp: str


class GraphPathState(TypedDict):
    entities: list[GraphEntityState]
    relations: list[GraphFactState]


class CapacityState(TypedDict):
    driver_available: bool
    vehicle_available: bool
    load_ratio: float
    station_load_ratio: float | None
    capacity_status: str
    risk_level: str
    reason: str | None
    provider_name: str


class RouteScoreComponentsState(TypedDict):
    normalized_minutes: str
    normalized_distance: str
    normalized_risk: str
    time_penalty: str
    distance_penalty: str
    risk_penalty: str


class RouteCandidateState(TypedDict):
    route_id: str
    route_name: str
    distance_km: str
    estimated_minutes: int
    risk_level: str
    available: bool
    reason: str | None
    score: str
    node_ids: NotRequired[list[str]]
    edge_ids: NotRequired[list[str]]
    objective: NotRequired[str | None]
    algorithm_version: NotRequired[str | None]
    road_network_version: NotRequired[int | None]
    visited_node_count: NotRequired[int | None]
    risk_cost: NotRequired[str | None]
    scoring_formula: NotRequired[str | None]
    score_components: NotRequired[RouteScoreComponentsState | None]


class PathState(TypedDict):
    objective: str
    node_ids: list[str]
    edge_ids: list[str]
    distance_km: str
    estimated_minutes: int
    risk_cost: str
    visited_node_count: int


class DispatchResultState(TypedDict):
    dispatch_id: int | None
    dispatch_no: str | None
    status: str
    target_route_id: str | None
    version: int | None
    executed: bool


class AuditChecksState(TypedDict):
    route_consistency: bool
    memory_consistency: bool
    fallback_consistency: bool
    dispatch_execution: bool


class AuditResultState(TypedDict):
    audit_status: str
    passed: bool
    reason: str
    checks: AuditChecksState
    dispatch_id: int | None
    requires_manual_review: bool
    audit_record_id: int | None


class DispatchGraphState(TypedDict):
    correlation_id: NotRequired[str | None]
    task_id: str
    order_id: int
    driver_id: str
    route_id: str
    anomaly_type: str
    anomaly_description: str
    vehicle_id: NotRequired[str]
    vehicle_status: NotRequired[VehicleRuntimeStatus]
    vehicle_weight_tons: NotRequired[str]
    normalized_anomaly: NotRequired[str]
    memory_results: NotRequired[list[MemoryRecallState]]
    graph_memory_facts: NotRequired[list[GraphFactState]]
    graph_memory_paths: NotRequired[list[GraphPathState]]
    graph_memory_used: NotRequired[bool]
    graph_memory_error: NotRequired[str | None]
    graph_memory_elapsed_ms: NotRequired[float]
    weather: NotRequired[str]
    road_condition: NotRequired[str]
    environment_risk: NotRequired[str]
    environment_provider: NotRequired[str]
    environment_elapsed_ms: NotRequired[float]
    capacity_state: NotRequired[CapacityState]
    cargo_weight_kg: NotRequired[str]
    cargo_type: NotRequired[str]
    origin_node_id: NotRequired[str]
    destination_node_id: NotRequired[str]
    incident_node_id: NotRequired[str | None]
    affected_edge_ids: NotRequired[list[str]]
    candidate_vehicles: NotRequired[list[dict[str, object]]]
    selected_vehicle_id: NotRequired[str]
    selected_driver_id: NotRequired[str]
    selected_vehicle_gross_weight_tons: NotRequired[str]
    vehicle_reassigned: NotRequired[bool]
    pickup_route: NotRequired[PathState | None]
    blocked_edge_ids: NotRequired[list[str]]
    original_path: NotRequired[PathState | None]
    recommended_path: NotRequired[PathState | None]
    routing_algorithm: NotRequired[str]
    routing_status: NotRequired[str]
    road_network_version: NotRequired[int]
    distance_delta_km: NotRequired[str]
    eta_delta_minutes: NotRequired[int]
    road_network_nodes: NotRequired[list[dict[str, object]]]
    road_network_edges: NotRequired[list[dict[str, object]]]
    candidate_routes: NotRequired[list[RouteCandidateState]]
    recommended_route: NotRequired[str]
    identified_issue: NotRequired[str]
    issue_subtype: NotRequired[str]
    recommended_action: NotRequired[str]
    analysis_mode: NotRequired[str]
    decision: NotRequired[str]
    decision_reason: NotRequired[str]
    memory_adopted: NotRequired[bool]
    adopted_memory_id: NotRequired[str | None]
    fallback_used: NotRequired[bool]
    fallback_reason: NotRequired[str]
    dispatch_version: NotRequired[int]
    dispatch_result: NotRequired[DispatchResultState]
    audit_result: NotRequired[AuditResultState | None]
    requires_manual_review: NotRequired[bool]
    error_code: NotRequired[str]
    error_message: NotRequired[str]
    started_at: NotRequired[str]
    completed_at: NotRequired[str]
    last_completed_node: NotRequired[str]
    completed_node_count: NotRequired[int]
