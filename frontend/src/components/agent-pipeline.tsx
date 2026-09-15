import { useState } from "react";
import { Check, ChevronDown, CircleAlert, Clock3, Play } from "lucide-react";
import { StatusPill } from "./status-pill";
import type { AgentRun } from "../types/dispatch";

function AgentGlyph({ status }: { status: AgentRun["status"] }) {
  if (status === "RUNNING") return <Play size={13} />;
  if (status === "FALLBACK" || status === "FAILED") return <CircleAlert size={13} />;
  if (status === "WAITING") return <Clock3 size={13} />;
  return <Check size={13} />;
}

export function AgentPipeline({ agents, onReplay }: { agents: AgentRun[]; onReplay?: () => void }) {
  const firstFailedId = agents.find((agent) => agent.status === "FAILED")?.id ?? null;
  const [selectedAgentId, setSelectedAgentId] = useState<string | null | undefined>(undefined);
  const openAgentId = selectedAgentId === undefined ? firstFailedId : selectedAgentId;

  return <section className="pipeline-panel" aria-labelledby="agent-pipeline-title"><div className="panel-heading"><div><p className="eyebrow">LangGraph 执行过程</p><h2 id="agent-pipeline-title">智能体流水线</h2></div>{onReplay && <button className="button-secondary replay" onClick={onReplay}><Play size={14}/>重新播放</button>}</div>
    <div className="pipeline-list">{agents.map((agent, index) => {
      const expanded = openAgentId === agent.id;
      const detailId = `agent-work-${agent.id}`;
      return <article className={`pipeline-item${expanded ? " is-expanded" : ""}`} key={agent.id}>
      <div className={`pipeline-node pipeline-${agent.status.toLowerCase()}`}><AgentGlyph status={agent.status}/></div>
      {index < agents.length - 1 && <div className="pipeline-connector" />}
      <div className="pipeline-copy"><div className="pipeline-title"><strong>{agent.name}</strong><StatusPill status={agent.status}/></div><span>{agent.output}</span>{agent.detail && <small>{agent.detail}</small>}</div><time>{agent.elapsed}</time>
      {agent.work && <button
        type="button"
        className="pipeline-work-toggle"
        aria-label={`${expanded ? "收起" : "查看"}${agent.name}工作详情`}
        aria-expanded={expanded}
        aria-controls={detailId}
        onClick={() => setSelectedAgentId(expanded ? null : agent.id)}
      ><ChevronDown size={14} /></button>}
      {agent.work && expanded && <div className="pipeline-work-detail" id={detailId}>
        <div className="pipeline-work-flow">
          <div><b>01</b><span><small>读取信息</small><strong>{agent.work.input}</strong></span></div>
          <div><b>02</b><span><small>执行动作</small><strong>{agent.work.action}</strong></span></div>
          <div><b>03</b><span><small>输出结果</small><strong>{agent.work.result}</strong></span></div>
        </div>
        {agent.work.evidence.length > 0 && <div className="pipeline-evidence"><p>关键证据</p><dl>{agent.work.evidence.map((item) => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl></div>}
        <div className="pipeline-event-meta"><code>{agent.work.eventType}</code><span>事件 {agent.work.eventId}</span><span>耗时 {agent.elapsed}</span></div>
      </div>}
    </article>;
    })}</div>
  </section>;
}
