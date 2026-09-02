export type DataProvenance = "LIVE_API" | "LIVE_EVENT" | "VERIFIED_ACCEPTANCE" | "DEMO_DATA";

export interface VerifiedMetric {
  label: string;
  value: string;
  detail: string;
  group: "memory" | "runtime" | "performance" | "reliability";
}

export interface GraphEntityView {
  id: string;
  type: "Driver" | "Vehicle" | "Route" | "Weather" | "Anomaly" | "Resolution";
  label: string;
  properties: Record<string, unknown>;
}

export interface GraphRelationView {
  id: string;
  sourceId: string;
  targetId: string;
  type: "DRIVES" | "HAS_RISK_ON" | "HIGH_RISK_WHEN" | "ALTERNATIVE_TO" | "RESOLVED_BY";
  confidence: number;
  source: string;
  evidence: string;
  controlVersion: number;
  projectionStatus: string;
}

export interface GraphPathView {
  id: string;
  entityIds: string[];
  relationIds: string[];
  hopCount: number;
}

export interface GraphMemoryViewModel {
  provenance: DataProvenance;
  used: boolean;
  elapsedMs: number | null;
  error: string | null;
  entities: GraphEntityView[];
  relations: GraphRelationView[];
  paths: GraphPathView[];
}
