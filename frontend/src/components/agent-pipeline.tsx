import { Check, CircleAlert, Clock3, Play } from "lucide-react";
import { StatusPill } from "./status-pill";
import type { AgentRun } from "../types/dispatch";

function AgentGlyph({ status }: { status: AgentRun["status"] }) {
  if (status === "RUNNING") return <Play size={13} />;
  if (status === "FALLBACK") return <CircleAlert size={13} />;
  if (status === "WAITING") return <Clock3 size={13} />;
  return <Check size={13} />;
}

export function AgentPipeline({ agents, onReplay }: { agents: AgentRun[]; onReplay?: () => void }) {
  return <section className="pipeline-panel" aria-labelledby="agent-pipeline-title"><div className="panel-heading"><div><p className="eyebrow">LangGraph 执行过程</p><h2 id="agent-pipeline-title">智能体流水线</h2></div>{onReplay && <button className="button-secondary replay" onClick={onReplay}><Play size={14}/>重新播放</button>}</div>
    <div className="pipeline-list">{agents.map((agent, index) => <div className="pipeline-item" key={agent.id}>
      <div className={`pipeline-node pipeline-${agent.status.toLowerCase()}`}><AgentGlyph status={agent.status}/></div>
      {index < agents.length - 1 && <div className="pipeline-connector" />}
      <div className="pipeline-copy"><div className="pipeline-title"><strong>{agent.name}</strong><StatusPill status={agent.status}/></div><span>{agent.output}</span>{agent.detail && <small>{agent.detail}</small>}</div><time>{agent.elapsed}</time>
    </div>)}</div>
  </section>;
}
