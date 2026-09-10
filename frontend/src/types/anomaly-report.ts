export type AnomalyReportType =
  | "ROAD_BLOCKED"
  | "ROAD_HAZARD"
  | "VEHICLE_BREAKDOWN"
  | "WEATHER"
  | "CARGO"
  | "CAPACITY"
  | "OTHER";

export type ReportedVehicleStatus =
  | "NORMAL"
  | "BROKEN"
  | "UNAVAILABLE"
  | "MAINTENANCE";

export type AnomalyReportSeverity = "LOW" | "MEDIUM" | "HIGH";

export interface AnomalyReportFormInput {
  source_task_id: string;
  anomaly_type: AnomalyReportType;
  description: string;
  location_text: string;
  reported_vehicle_status: ReportedVehicleStatus;
  severity: AnomalyReportSeverity;
  incident_node_id?: string | null;
  affected_edge_id?: string | null;
}

export interface AnomalyReportRequest extends AnomalyReportFormInput {
  idempotency_key: string;
}

export interface AnomalyReportResponse {
  anomaly_id: number;
  anomaly_no: string;
  task_id: string;
  status: string;
  accepted: boolean;
  duplicate: boolean;
  message: string;
}

export interface RetryableAnomalyReportError {
  code: "REPORT_QUEUE_UNAVAILABLE";
  message: string;
  anomaly_id: number;
  anomaly_no: string;
  task_id: string;
  retryable: true;
}
