import { BrainCircuit, ChevronRight, CloudRain, Database, Gauge, Route, ShieldCheck, Workflow } from "lucide-react";
import { useCallback, useState } from "react";
import { Link } from "react-router-dom";

import { Metric } from "../components/workspace-ui";
import { runtimeConfig } from "../config/runtime";
import { DEMO_TASK_ID, demoAgentSnapshots, isDemoSnapshotEnabled } from "../demo/demo-snapshots";
import { useTaskEvents } from "../hooks/use-task-events";
import { describeAgentEvent } from "../utils/agent-event";
import { localizeStatus } from "../utils/presentation-labels";

const agentIcons = {
  intake: Workflow,
  entity_memory: BrainCircuit,
  graph_memory: BrainCircuit,
  environment: CloudRain,
  capacity: Gauge,
  routing: Route,
  dispatch: Database,
  audit: ShieldCheck,
} as const;

export function AgentsPage() {
  const [active, setActive] = useState("graph_memory");
  const [taskId, setTaskId] = useState("");
  const onTerminal = useCallback(() => undefined, []);
  const taskRun = useTaskEvents(taskId, onTerminal);
  const showDemoSnapshot = isDemoSnapshotEnabled(runtimeConfig) && !taskId.trim();
  const agents = demoAgentSnapshots.map((spec) => {
    const icon = agentIcons[spec.id as keyof typeof agentIcons] ?? Workflow;
    if (showDemoSnapshot) return { ...spec, icon };
    const live = taskRun.agents.find((agent) => agent.id === spec.id);
    const latest = [...taskRun.events].reverse().find((event) => event.node === spec.id);
    return { ...spec, icon, status: live?.status ?? "WAITING", latency: "—", detail: latest ? describeAgentEvent(spec.id, latest.event_type, latest.data) : "等待真实任务事件。" };
  });
  const selected = agents.find((item) => item.id === active) ?? agents[0];
  const Icon = selected.icon;
  const graphEvent = [...taskRun.events].reverse().find((event) => event.node === "graph_memory");
  const graphFacts = Array.isArray(graphEvent?.data.graph_memory_facts) ? graphEvent.data.graph_memory_facts.length : showDemoSnapshot ? 5 : 0;
  const graphPaths = Array.isArray(graphEvent?.data.graph_memory_paths) ? graphEvent.data.graph_memory_paths.length : showDemoSnapshot ? 2 : 0;
  return <div className="workspace-page">
    <section className="agent-layout"><aside className="agent-rail"><div className="agent-rail-source"><p className="eyebrow">八个智能体</p><span className={`source-label ${showDemoSnapshot ? "demo" : "live"}`}>{showDemoSnapshot ? "演示数据" : "实时事件"}</span></div>{agents.map((agent, index) => { const AgentIcon = agent.icon; return <button key={agent.id} className={active === agent.id ? "agent-rail-item selected" : "agent-rail-item"} onClick={() => setActive(agent.id)}><span>{String(index + 1).padStart(2, "0")}</span><AgentIcon size={16}/><strong>{agent.name}</strong><i className={`status-dot ${agent.status.toLowerCase()}`}/></button>; })}</aside>
      <section className="agent-detail"><div className="panel-heading"><div><p className="eyebrow">智能体运行态 / {selected.id.toUpperCase()}</p><h2><Icon size={19}/>{selected.name}</h2></div><span className={`status-pill status-${selected.status.toLowerCase()}`}>{localizeStatus(selected.status)}</span></div>
        {runtimeConfig.dataMode === "api" ? <label className="task-event-query">任务 ID<input value={taskId} onChange={(event) => setTaskId(event.target.value)} placeholder="TASK-..."/><span>{localizeStatus(taskRun.connection)}</span></label> : null}
        <p className="agent-description">{selected.detail}</p><div className="agent-stat-grid"><span>职责<strong>{selected.role}</strong></span><span>输入<strong>{selected.input}</strong></span><span>耗时<strong>{selected.latency}</strong></span><span>状态<strong>{localizeStatus(selected.status)}</strong></span></div>
        {selected.id === "graph_memory" ? <div className="graph-agent-detail"><span>图实体<strong>{graphFacts ? graphFacts + 1 : 0}</strong></span><span>关系<strong>{graphFacts}</strong></span><span>路径<strong>{graphPaths}</strong></span><span>故障降级<strong>未使用图记忆 · 下游继续执行</strong></span></div> : null}
        <div className="execution-block"><div><p className="eyebrow">最近一次执行</p><h3>{showDemoSnapshot ? DEMO_TASK_ID : taskId || "等待任务 ID"}</h3></div><div className="execution-line"><span>来源</span><b>{showDemoSnapshot ? "演示数据" : "后端 WebSocket"}</b><span>事件</span><b>{selected.detail}</b></div><Link to="/dispatch" className="text-action">发起新的智能调度 <ChevronRight size={14}/></Link></div>
      </section></section>
    <section className="metrics-grid workspace-metrics agent-metrics"><Metric label="八智能体拓扑" value="8 / 8" note="V2 规范顺序" tone="teal"/><Metric label="图记忆" value={String(graphFacts)} note={showDemoSnapshot ? "有界事实 · 演示数据" : "有界事实"} tone="violet"/><Metric label="事件来源" value={showDemoSnapshot ? "演示" : localizeStatus(taskRun.connection)} note={showDemoSnapshot ? "演示数据" : "WebSocket"}/><Metric label="故障降级" value="安全" note={showDemoSnapshot ? "环境节点继续执行 · 演示数据" : "环境节点继续执行"} tone="teal"/></section>
  </div>;
}
