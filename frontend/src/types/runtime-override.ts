export type VehicleRuntimeStatus = "NORMAL" | "BROKEN" | "UNAVAILABLE" | "MAINTENANCE";
export type RuntimeOverrideStatus = "PENDING" | "APPLYING" | "APPLIED" | "REJECTED" | "CONFLICT" | "PARTIAL" | "FAILED";
export type RuntimeInterventionEligibility = "ELIGIBLE" | "NOT_STABLE" | "TERMINAL" | "NO_PERMISSION" | "WRONG_BOUNDARY" | "BUSY";
export type OverrideSubmissionState = "IDLE" | "SUBMITTING" | "APPLIED" | "CONFLICT" | "BUSY" | "REJECTED" | "PARTIAL" | "FAILED";

export interface RuntimeOverrideRequest {
  idempotency_key: string;
  entity_type: "Vehicle";
  entity_id: string;
  field: "status";
  old_value: "NORMAL";
  new_value: Exclude<VehicleRuntimeStatus, "NORMAL">;
  reason: string;
  expected_version: number;
  expected_next_node: "capacity";
}

export interface RuntimeOverrideResponse {
  override_id: string;
  thread_id: string;
  task_id: string;
  operator_id: string;
  operator_role: string;
  status: RuntimeOverrideStatus;
  decision: string | null;
  expected_version: number;
  expected_next_node: string | null;
  before_state_version: number | null;
  after_state_version: number | null;
  entity_type: string;
  entity_id: string;
  field: string;
  old_value: string;
  new_value: string;
  reason: string;
  source_checkpoint_id: string | null;
  result_checkpoint_id: string | null;
  event_status: string;
  error_code: string | null;
  requested_at: string;
  started_at: string | null;
  completed_at: string | null;
  replayed: boolean;
}

export type RuntimeOverrideDetail = RuntimeOverrideResponse;

export interface RuntimeInterventionTarget {
  entity_type: string;
  entity_id: string;
  display_name: string;
  field: string;
  current_value: string;
  allowed_new_values: string[];
}

export interface RuntimeInterventionContext {
  thread_id: string;
  task_id: string;
  runtime_status: string;
  state_version: number;
  current_node: string | null;
  next_node: string | null;
  canonical_checkpoint_id: string | null;
  checkpoint_available: boolean;
  eligibility: RuntimeInterventionEligibility;
  eligibility_reason_code: string | null;
  can_override: boolean;
  target: RuntimeInterventionTarget | null;
  observed_at: string;
}

export interface RuntimeOverrideHistory {
  thread_id: string;
  items: RuntimeOverrideDetail[];
}

export interface OverrideDialogSnapshot {
  threadId: string;
  taskId: string;
  checkpointId: string;
  expectedVersion: number;
  expectedNextNode: "capacity";
  entityType: "Vehicle";
  entityId: string;
  field: "status";
  oldValue: "NORMAL";
  newValue: Exclude<VehicleRuntimeStatus, "NORMAL">;
}
