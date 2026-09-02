export type WorkspaceReadProvenance = "LIVE" | "DEMO" | "MIXED";

export interface OverviewResponse {
  orders: number;
  anomalies: number;
  reviews: number;
  runtime_threads: number;
  provenance: WorkspaceReadProvenance;
}

export interface PageResponse<T> {
  items: T[];
  total: number;
  next_cursor: string | null;
  provenance: WorkspaceReadProvenance;
}

export interface OrderListItem {
  row_id: number;
  order_no: string;
  status: string;
  driver_id: string | null;
  vehicle_id: string | null;
  route_id: string | null;
  origin: string;
  destination: string;
  created_at: string;
  updated_at: string;
  anomaly_count: number;
  latest_task_id: string | null;
}

export interface AnomalyListItem {
  row_id: number;
  anomaly_no: string;
  order_no: string | null;
  driver_id: string | null;
  vehicle_id: string | null;
  route_id: string | null;
  latest_task_id: string | null;
  anomaly_type: string;
  risk: string;
  description: string;
  status: string;
  reported_at: string;
}

export interface ReviewListItem {
  row_id: number;
  task_id: string;
  order_no: string | null;
  risk: string | null;
  reason: string | null;
  vehicle_id: string | null;
  original_route_id: string | null;
  suggested_route_id: string | null;
  status: string;
  created_at: string;
  ai_analysis_reason: string | null;
  ai_recommended_action: string | null;
  ai_analysis_mode: string | null;
  issue_subtype: string | null;
}

export type MyTaskQueueState = "READY" | "WAITING" | "ACTIVE" | "ENDED";

export interface MyTaskListItem {
  row_id: number;
  task_id: string;
  order_no: string | null;
  risk: string | null;
  description: string | null;
  vehicle_id: string | null;
  original_route_id: string | null;
  suggested_route_id: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  origin: string | null;
  destination: string | null;
  publication_status: string;
  published_at: string | null;
  route_instruction: string | null;
}

export interface MyTaskSummary {
  total: number;
  ready: number;
  waiting: number;
  active: number;
  ended: number;
}

export interface MyTaskPageResponse extends PageResponse<MyTaskListItem> {
  summary: MyTaskSummary;
}

export interface RuntimeThreadListItem {
  row_id: number;
  thread_id: string;
  task_id: string;
  status: string;
  current_node: string | null;
  next_node: string | null;
  state_version: number;
  checkpoint_count: number;
  worker_consumer: string | null;
  terminal_at: string | null;
  updated_at: string;
}

export interface VectorMemoryListItem {
  memory_id: string | null;
  driver_id: string | null;
  route_id: string | null;
  anomaly_type: string | null;
  historical_resolution: string | null;
  created_at: string | null;
  projection_status: string | null;
}

export interface VectorMemoryPageResponse extends PageResponse<VectorMemoryListItem> {
  vector_dimension: number | null;
}

export interface PageFilters {
  limit?: number;
  cursor?: string | null;
}

export interface OrdersFilters extends PageFilters {
  query?: string;
  status?: string;
}

export interface AnomalyFilters extends PageFilters {
  query?: string;
  risk?: string;
  status?: string;
}

export interface RuntimeThreadFilters extends PageFilters {
  status?: string;
}

export interface MyTaskFilters extends PageFilters {
  state?: MyTaskQueueState;
}
