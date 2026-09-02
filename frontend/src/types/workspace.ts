export type DataProvenance = "LIVE" | "DEMO" | "MIXED" | "VERIFIED" | "STALE" | "NOT_EXPOSED";
export type ReadStateName = "LOADING" | "READY" | "EMPTY" | "NOT_EXPOSED" | "FORBIDDEN" | "ERROR" | "UNAVAILABLE";

export type ReadState<T> =
  | { state: "READY"; data: T }
  | { state: Exclude<ReadStateName, "READY">; data: null; message?: string };

export interface WorkspaceMetric {
  id: string;
  label: string;
  value: string | null;
  provenance: DataProvenance;
}

export interface WorkspaceTask {
  taskId: string;
  title: string;
  status: string;
  risk: string;
  waitingSince: string;
  detailHref?: string;
}

export interface DispatcherWorkspaceView {
  metrics: WorkspaceMetric[];
  tasks: WorkspaceTask[];
}
