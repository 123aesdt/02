import { ExternalLink } from "lucide-react";

import type { ObservabilityState, ObservabilitySummary, ObservabilityWindow } from "../types/observability";
import { mergeObservabilityMetrics } from "../demo/demo-snapshots";
import { ObservabilityTrend } from "./observability-trend";
import { localizeStatus } from "../utils/presentation-labels";

const metricDefinitions = [
  ["http_qps", "当前 QPS", (value: number) => value.toFixed(2)],
  ["http_p95", "API P95", (value: number) => `${(value * 1000).toFixed(0)} ms`],
  ["http_error_rate", "错误率", (value: number) => `${(value * 100).toFixed(2)}%`],
  ["agent_p95", "智能体 P95", (value: number) => `${(value * 1000).toFixed(0)} ms`],
  ["worker_pending", "Worker 待处理", (value: number) => value.toFixed(0)],
  ["worker_lag", "消息流延迟", (value: number) => value.toFixed(0)],
  ["graph_p95", "图记忆 P95", (value: number) => `${(value * 1000).toFixed(1)} ms`],
  ["checkpoint_p95", "检查点 P95", (value: number) => `${(value * 1000).toFixed(1)} ms`],
  ["override_success", "干预应用率", (value: number) => `${(value * 100).toFixed(1)}%`],
  ["memory_partial", "部分完成的记忆", (value: number) => value.toFixed(0)],
  ["dependency_up", "正常依赖数", (value: number) => value.toFixed(0)],
] as const;

interface Props {
  state: ObservabilityState;
  data: ObservabilitySummary | null;
  window: ObservabilityWindow;
  onWindowChange: (window: ObservabilityWindow) => void;
  demoFallback?: boolean;
}

export function LiveObservabilityPanel({ state, data, window, onWindowChange, demoFallback = false }: Props) {
  const presentation = mergeObservabilityMetrics(data?.metrics, demoFallback);
  const demoKeys = new Set(presentation.demoKeys);
  const hasDemoMetrics = demoKeys.size > 0;
  return <section className="workspace-panel live-observability-panel">
    <div className="panel-heading"><div><p className="eyebrow">实时可观测性</p><h2>生产遥测</h2></div><span className={`source-label ${hasDemoMetrics || state !== "LIVE" ? "demo" : "live"}`}>{localizeStatus(state)}{hasDemoMetrics ? ` · ${data ? "混合数据" : "演示数据"}` : ""}</span></div>
    <div className="observability-toolbar" role="group" aria-label="监控时间窗口">
      {(["5m", "15m", "1h"] as const).map((item) => <button key={item} type="button" className={window === item ? "active" : ""} onClick={() => onWindowChange(item)}>{item}</button>)}
      {data?.grafana_url ? <a href={data.grafana_url} target="_blank" rel="noreferrer">打开 Grafana <ExternalLink size={14}/></a> : null}
    </div>
    {state === "UNAVAILABLE" ? <p className="monitor-state-message">监控暂不可用</p> : null}
    {state === "NO_PERMISSION" ? <p className="monitor-state-message">需要监控读取权限</p> : null}
    {state === "STALE" ? <p className="monitor-state-message">实时遥测数据已陈旧；当前展示最后一组安全样本。</p> : null}
    {hasDemoMetrics ? <p className="monitor-state-message">当前无企业遥测的指标使用演示样本补齐；每项演示值均已标识。</p> : null}
    {data || hasDemoMetrics ? <div className="live-metric-grid">{metricDefinitions.map(([key, label, format]) => {
      const value = presentation.metrics[key];
      return <article key={key}><span>{label}</span><strong>{typeof value === "number" ? format(value) : "—"}</strong>{demoKeys.has(key) ? <small className="metric-demo-marker">演示</small> : null}<ObservabilityTrend value={value}/></article>;
    })}</div> : null}
    {data?.series?.dependency_up ? <div className="dependency-state-strip">{(["mysql", "redis", "qdrant", "neo4j"] as const).map((dependency) => {
      const value = data.series?.dependency_up?.[dependency];
      const label = dependency === "mysql" ? "MySQL" : dependency === "qdrant" ? "Qdrant" : dependency === "neo4j" ? "Neo4j" : "Redis";
      return <span key={dependency} className={value === 1 ? "up" : "down"}>{label} {value === 1 ? "正常" : "异常"}</span>;
    })}</div> : null}
  </section>;
}
