import type { ApiClient } from "./client";

export interface CreateDispatchTaskRequest {
  order_id: number;
  anomaly_id: number | null;
  driver_id: string;
  vehicle_id: string;
  route_id: string;
  anomaly_type: string;
  anomaly_description: string;
  idempotency_key: string;
  assignee_employee_id?: string;
}

export interface CreateDispatchTaskResponse {
  task_id: string;
  order_id: number;
  status: string;
  accepted: boolean;
  duplicate: boolean;
  message: string;
}

export interface TaskStatusResponse {
  task_id: string;
  order_id: number;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  ready: boolean;
  requires_manual_review: boolean;
}

export interface DispatchResultResponse {
  dispatch_id: number;
  dispatch_no: string;
  original_route_id: string | null;
  target_route_id: string | null;
  status: string;
  decision_reason: string | null;
  fallback_used: boolean;
  fallback_reason: string | null;
  version: number;
  executed: boolean;
}

export interface PublicationResultResponse {
  status: string;
  route_id: string | null;
  route_instruction: string | null;
  published_at: string | null;
  published_by: string | null;
  recipient_employee_id: string | null;
  recipient_display_name: string | null;
}

export interface DispatchPublicationResponse extends PublicationResultResponse {
  task_id: string;
  dispatch_id: number;
  route_id: string;
  route_instruction: string;
  published_at: string;
  published_by: string;
  recipient_employee_id: string;
  recipient_display_name: string;
  duplicate: boolean;
}

export interface AuditResultResponse {
  result: string;
  reason: string;
  dispatch_id: number;
  created_at: string;
}


export interface FleetScoreComponentsResponse {
  eta_penalty: string | null;
  distance_penalty: string | null;
  load_penalty: string | null;
  road_risk_penalty: string | null;
  same_station_bonus: string | null;
  cargo_exact_match_bonus: string | null;
}

export interface RouteScoreComponentsResponse {
  normalized_minutes: string | null;
  normalized_distance: string | null;
  normalized_risk: string | null;
  time_penalty: string | null;
  distance_penalty: string | null;
  risk_penalty: string | null;
}

export interface PathResponse {
  objective: string;
  node_ids: string[];
  edge_ids: string[];
  distance_km: string;
  estimated_minutes: number;
  risk_cost: string;
  visited_node_count: number;
  scoring_formula: string | null;
}

export interface VehicleCandidateResponse {
  vehicle_id: string;
  driver_id: string | null;
  vehicle_status: string | null;
  driver_status: string | null;
  remaining_capacity_kg: string | null;
  gross_weight_tons: string | null;
  cargo_capability: string | null;
  pickup_route: PathResponse | null;
  pickup_distance_km: string | null;
  pickup_eta_minutes: number | null;
  score: string | null;
  score_components: FleetScoreComponentsResponse | null;
  scoring_formula: string | null;
  eligible: boolean | null;
  exclusion_reasons: string[];
}

export interface VehicleAllocationResponse {
  original_vehicle_id: string | null;
  target_vehicle_id: string | null;
  target_driver_id: string | null;
  vehicle_reassigned: boolean;
  candidate_vehicles: VehicleCandidateResponse[];
  pickup_route: PathResponse | null;
  scoring_formula: string;
}

export interface RoadNodeResponse {
  node_id: string;
  name: string;
  x_km: string;
  y_km: string;
  node_type: string;
}

export interface RoadEdgeResponse {
  edge_id: string;
  name: string;
  from_node_id: string;
  to_node_id: string;
  distance_km: string;
  base_minutes: number;
  road_level: string;
  risk_level: string;
  status: string;
  congestion_factor: string;
  weight_limit_tons: string;
  bidirectional: boolean;
  version: number;
}

export interface RouteCandidateResponse {
  route_id: string;
  route_name: string;
  objective: string;
  node_ids: string[];
  edge_ids: string[];
  distance_km: string;
  estimated_minutes: number;
  risk_level: string;
  risk_cost: string;
  visited_node_count: number;
  available: boolean;
  reason: string | null;
  score: string;
  score_components: RouteScoreComponentsResponse | null;
  scoring_formula: string;
  algorithm_version: string | null;
  road_network_version: number | null;
}

export interface GeoPointResponse {
  node_id: string | null;
  longitude: string;
  latitude: string;
}

export interface RealRoadRouteResponse {
  provider: "AMAP";
  source: "AMAP_WEB_SERVICE" | "CLIENT_WAYPOINT_FALLBACK";
  status: "VERIFIED" | "CLIENT_MATCH_REQUIRED";
  coordinate_system: "GCJ02";
  mapping_version: string;
  distance_meters: number | null;
  duration_seconds: number | null;
  waypoints: GeoPointResponse[];
  polyline: GeoPointResponse[];
  fallback_reason: string | null;
}

export interface RoutePlanResponse {
  original_path: PathResponse | null;
  recommended_path: PathResponse | null;
  candidate_routes: RouteCandidateResponse[];
  blocked_edge_ids: string[];
  distance_delta_km: string | null;
  eta_delta_minutes: number | null;
  visited_node_count: number | null;
  routing_status: string | null;
  algorithm: string;
  road_network_version: number | null;
  network_nodes: RoadNodeResponse[];
  network_edges: RoadEdgeResponse[];
  real_road_route?: RealRoadRouteResponse | null;
}

export interface DispatchImpactResponse {
  incident_vehicle_id: string;
  replacement_vehicle_id: string;
  replacement_driver_id: string | null;
  pickup_distance_km: string | null;
  pickup_eta_minutes: number | null;
  route_distance_delta_km: string | null;
  route_eta_delta_minutes: number | null;
  total_distance_delta_km: string | null;
  total_delay_minutes: number | null;
  calculation_status: "CALCULATED" | "PARTIAL";
}

export interface TaskResultResponse {
  task_id: string;
  order_id: number;
  ready: boolean;
  status: string;
  anomaly_type?: string | null;
  dispatch: DispatchResultResponse | null;
  audit: AuditResultResponse | null;
  publication?: PublicationResultResponse | null;
  vehicle_allocation?: VehicleAllocationResponse | null;
  route_plan?: RoutePlanResponse | null;
  dispatch_impact?: DispatchImpactResponse | null;
}

export interface DispatchAdapter {
  createDispatchTask(request: CreateDispatchTaskRequest, signal?: AbortSignal): Promise<CreateDispatchTaskResponse>;
  getTaskStatus(taskId: string, signal?: AbortSignal): Promise<TaskStatusResponse>;
  getTaskResult(taskId: string, signal?: AbortSignal): Promise<TaskResultResponse>;
  publishDispatchTask(taskId: string, signal?: AbortSignal): Promise<DispatchPublicationResponse>;
}

export class RealDispatchAdapter implements DispatchAdapter {
  constructor(private readonly client: ApiClient) {}

  async createDispatchTask(request: CreateDispatchTaskRequest, signal?: AbortSignal): Promise<CreateDispatchTaskResponse> {
    const response = await this.client.request<CreateDispatchTaskResponse>("/api/v1/dispatch-tasks", {
      method: "POST",
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    return response.data;
  }

  async getTaskStatus(taskId: string, signal?: AbortSignal): Promise<TaskStatusResponse> {
    const response = await this.client.request<TaskStatusResponse>(`/api/v1/dispatch-tasks/${encodeURIComponent(taskId)}`, { signal });
    return response.data;
  }

  async getTaskResult(taskId: string, signal?: AbortSignal): Promise<TaskResultResponse> {
    const response = await this.client.request<TaskResultResponse>(`/api/v1/dispatch-tasks/${encodeURIComponent(taskId)}/result`, { signal });
    return response.data;
  }

  async publishDispatchTask(taskId: string, signal?: AbortSignal): Promise<DispatchPublicationResponse> {
    const response = await this.client.request<DispatchPublicationResponse>(
      `/api/v1/dispatch-tasks/${encodeURIComponent(taskId)}/publish`,
      { method: "POST", signal },
    );
    return response.data;
  }
}
