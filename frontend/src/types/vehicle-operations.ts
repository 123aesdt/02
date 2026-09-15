export interface OperationMapNode {
  node_id: string;
  name: string;
  x_km: string;
  y_km: string;
  node_type: string;
}

export interface OperationMapEdge {
  edge_id: string;
  name: string;
  from_node_id: string;
  to_node_id: string;
  road_level: string;
  status: string;
}

export interface OperationVehicle {
  vehicle_id: string;
  plate_no: string;
  status: string;
  current_node_id: string;
  max_load_kg?: string;
  current_load_kg?: string;
  assigned_driver_id?: string | null;
  status_reason?: string | null;
  available_after?: string | null;
  is_incident: boolean;
  is_replacement: boolean;
}

export interface OperationRoute {
  kind: "REPLACEMENT" | "RESCUE" | "TOW" | "INTERRUPTED";
  edge_ids: string[];
  node_ids: string[];
  status: string;
}

export interface OperationStage {
  key: string;
  title: string;
  status: "COMPLETED" | "ACTIVE" | "WAITING" | "FAILED" | "CANCELLED" | "SKIPPED";
  detail: string;
}

export interface VehicleOperationSnapshot {
  task_id: string;
  generated_at: string;
  incident: {
    status: string;
    risk: string;
    vehicle_id: string;
    replacement_vehicle_id: string | null;
    location_node_id: string;
    fault_code: string;
    cargo: string;
  };
  nodes: OperationMapNode[];
  edges: OperationMapEdge[];
  vehicles: OperationVehicle[];
  routes: OperationRoute[];
  rescue: {
    mission_no: string;
    status: string;
    progress_percent: number;
    rescue_unit_id: string;
    incident_node_id: string;
    station_node_id: string;
    outbound_edge_ids?: string[];
    tow_edge_ids?: string[];
    next_transition_at: string | null;
  };
  maintenance: {
    order_no: string;
    vehicle_id: string;
    bay_code: string | null;
    status: string;
    fault_code: string;
    diagnosis: string | null;
    repair_minutes: number;
    manual_inspection_required: boolean;
    inspection_result: string | null;
    progress_percent: number;
    countdown_seconds: number | null;
    available_after: string | null;
  };
  stages: OperationStage[];
  timeline: Array<{
    event_id: string;
    event_type: string;
    label: string;
    timestamp: string;
    payload: Record<string, unknown>;
  }>;
}
