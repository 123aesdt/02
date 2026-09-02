import { Activity, CheckCircle2, Database, Server } from "lucide-react";
import { useEffect, useState } from "react";

import { VerifiedBaselinePanel } from "../components/verified-baseline-panel";
import { LiveObservabilityPanel } from "../components/live-observability-panel";
import { runtimeConfig } from "../config/runtime";
import { useObservability } from "../hooks/use-observability";
import { getBackendHealth, type BackendHealthResponse } from "../services/dispatch-service";
import type { ObservabilityWindow } from "../types/observability";
import { localizeStatus } from "../utils/presentation-labels";

export function MonitorPage() {
  const [health, setHealth] = useState<BackendHealthResponse | null>(null);
  const [error, setError] = useState(false);
  const [observabilityWindow, setObservabilityWindow] = useState<ObservabilityWindow>("5m");
  const observability = useObservability(observabilityWindow);
  useEffect(() => {
    if (runtimeConfig.dataMode !== "api") return undefined;
    const controller = new AbortController();
    void getBackendHealth(controller.signal).then(setHealth, () => setError(true));
    return () => controller.abort();
  }, []);
  const source = runtimeConfig.dataMode === "api" ? "实时 API" : "演示数据";
  const backendState = runtimeConfig.dataMode === "mock" ? "DEMO DATA" : error ? "UNAVAILABLE" : health ? "CONNECTED" : "CHECKING";
  const runtime = health?.runtime;
  const services = [
    ["Backend", backendState, health?.version ?? "—"],
    ["Worker-1", runtimeConfig.dataMode === "mock" ? "DEMO DATA" : "NOT EXPOSED", "消费者状态"],
    ["Worker-2", runtimeConfig.dataMode === "mock" ? "DEMO DATA" : "NOT EXPOSED", "消费者状态"],
    ["Redis", runtime?.redis ? "CONFIGURED" : runtimeConfig.dataMode === "mock" ? "DEMO DATA" : "NOT EXPOSED", runtime?.redis ?? "—"],
    ["MySQL", runtime?.database ? "CONFIGURED" : runtimeConfig.dataMode === "mock" ? "DEMO DATA" : "NOT EXPOSED", runtime?.database ?? "—"],
    ["Qdrant", runtime?.qdrant ? "CONFIGURED" : runtimeConfig.dataMode === "mock" ? "DEMO DATA" : "NOT EXPOSED", runtime?.qdrant ?? "—"],
    ["Neo4j", runtime?.graph_memory ? "CONFIGURED" : runtimeConfig.dataMode === "mock" ? "DEMO DATA" : "NOT EXPOSED", runtime?.graph_memory ?? "—"],
  ];
  return <div className="workspace-page monitor-v2-page">
    <LiveObservabilityPanel state={observability.state} data={observability.data} window={observabilityWindow} onWindowChange={setObservabilityWindow} demoFallback/>
    <section className="workspace-panel"><div className="panel-heading"><div><p className="eyebrow">基础设施健康</p><h2>V2 服务拓扑</h2></div><span className={`source-label ${runtimeConfig.dataMode === "api" ? "live" : "demo"}`}>{source}</span></div><p className="monitor-disclaimer">仅后端 `/health` 返回的配置可标记为已连接或已配置；未暴露的 Worker/依赖实时探针明确显示“未开放”。</p><div className="health-list v2-health-list">{services.map(([name, status, detail]) => <div key={name}><CheckCircle2 size={16}/><span>{name}</span><small>{detail}</small><b className={status === "UNAVAILABLE" ? "text-danger" : status === "NOT EXPOSED" ? "text-amber" : ""}>{localizeStatus(status)}</b></div>)}</div></section>
    <section className="monitor-grid"><article className="workspace-panel"><div className="panel-heading"><div><p className="eyebrow">运行态控制</p><h2>检查点与干预</h2></div><Activity size={18}/></div><div className="reliability-grid v2-runtime-modules"><span>检查点<strong>已持久化</strong><small>Redis 异步保存器</small></span><span>运行态干预<strong>可审计</strong><small>后端资格校验</small></span><span>干预历史<strong>版本化</strong><small>MySQL 事实来源</small></span></div></article><article className="workspace-panel"><div className="panel-heading"><div><p className="eyebrow">记忆层</p><h2>共享记忆</h2></div><Database size={18}/></div><div className="memory-layer-health"><span><b>向量记忆</b><small>Qdrant · 语义</small></span><span><b>图记忆</b><small>Neo4j · 关系</small></span><span><b>共享控制</b><small>MySQL · 规范数据</small></span></div></article><article className="workspace-panel"><div className="panel-heading"><div><p className="eyebrow">WORKER 运行态</p><h2>恢复模型</h2></div><Server size={18}/></div><div className="memory-layer-health"><span><b>Redis 消息流</b><small>消费者组</small></span><span><b>待处理恢复</b><small>XAUTOCLAIM</small></span><span><b>终态确认</b><small>持久化状态完成后确认</small></span></div></article></section>
    <VerifiedBaselinePanel/>
  </div>;
}
