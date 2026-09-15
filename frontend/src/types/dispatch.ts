export type AgentStatus = "SUCCESS" | "FALLBACK" | "APPROVED" | "RUNNING" | "WAITING" | "FAILED";

export interface AnomalyRow {
  id: string;
  taskId: string;
  orderId: string;
  type: string;
  risk: "HIGH" | "MEDIUM" | "LOW";
  driver: string;
  route: string;
  status: string;
  occurredAt: string;
}

export interface AgentRun {
  id: string;
  name: string;
  status: AgentStatus;
  elapsed: string;
  output: string;
  detail?: string;
  work?: AgentWork;
}

export interface AgentEvidence {
  label: string;
  value: string;
}

export interface AgentWork {
  input: string;
  action: string;
  result: string;
  evidence: AgentEvidence[];
  eventType: string;
  eventId: string;
}

export interface RouteCandidate {
  id: string;
  label: string;
  distance: string;
  eta: string;
  risk: "LOW" | "MEDIUM" | "HIGH";
  score: number;
  state?: "RECOMMENDED" | "UNAVAILABLE";
  reason?: string;
}

export interface DashboardSnapshot {
  metrics: { label: string; value: string; note: string; tone?: string }[];
  recentAnomalies: AnomalyRow[];
  agents: AgentRun[];
}

export interface DispatchDetail {
  taskId: string;
  orderId: string;
  driver: string;
  vehicle: string;
  originalRoute: string;
  anomaly: string;
  severity: "HIGH";
  status: string;
  description: string;
  candidates: RouteCandidate[];
  memory: { memoryId: string; driver: string; route: string; anomaly: string; resolution: string; similarity: string; adopted: boolean };
  graphMemory: { used: boolean; entities: string[]; facts: string[]; paths: string[] };
  environment: { weather: string; road: string; risk: string; provider: string; timeout: string; fallback: string; elapsed: string; circuit: string };
  capacity: { driver: string; vehicle: string; vehicleLoad: number; stationLoad: number; status: string; risk: string };
  decisionReason: string;
  agents: AgentRun[];
  dispatch: { decision: string; originalRoute: string; targetRoute: string; executed: boolean; version: number; memoryAdopted: boolean; fallbackUsed: boolean };
  audit: { status: string; checks: string[] };
}
