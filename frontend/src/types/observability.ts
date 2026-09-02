export type ObservabilityWindow = "5m" | "15m" | "1h";
export type ObservabilityState = "LIVE" | "STALE" | "UNAVAILABLE" | "NO_PERMISSION";

export interface ObservabilitySummary {
  state: "LIVE" | "STALE";
  window: ObservabilityWindow;
  timestamp: string;
  metrics: Record<string, number | null>;
  series?: Record<string, Record<string, number>>;
  grafana_url: string | null;
}
