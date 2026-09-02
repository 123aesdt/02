import { Bot, BrainCircuit, Database, GitBranch, History, Network, Server, Workflow } from "lucide-react";
import { Link } from "react-router-dom";

import { verifiedV2Metrics } from "../mocks/v2-product-data";

const capabilities = [
  { label: "8 个智能体", detail: "LangGraph 执行流水线", to: "/agents", icon: Bot },
  { label: "向量记忆", detail: "Qdrant 语义召回", to: "/memory", icon: BrainCircuit },
  { label: "图记忆", detail: "Neo4j 有界路径", to: "/memory", icon: Network },
  { label: "共享记忆", detail: "MySQL 控制平面", to: "/memory", icon: Database },
  { label: "运行线程", detail: "持久化检查点", to: "/dispatch", icon: Workflow },
  { label: "运行态干预", detail: "全程审计", to: "/dispatch", icon: GitBranch },
  { label: "干预历史", detail: "版本化证据", to: "/dispatch", icon: History },
  { label: "11 项服务", detail: "Redis · MySQL · Qdrant · Neo4j · Prometheus · Grafana", to: "/monitor", icon: Server },
];

export function V2CapabilitySummary() {
  const memoryBaseline = verifiedV2Metrics.find((item) => item.label === "向量 Top-1");
  return <section className="workspace-panel v2-capability-panel">
    <div className="panel-heading"><div><p className="eyebrow">COUNTYFLOW V2</p><h2>V2 能力总览</h2></div><span className="source-label verified">已通过验收</span></div>
    <div className="v2-capability-grid">{capabilities.map(({ label, detail, to, icon: Icon }) => <Link to={to} key={label} className="v2-capability-item"><Icon size={16}/><span><strong>{label}</strong><small>{detail}</small></span></Link>)}</div>
    <div className="v2-summary-foot"><span>最新向量回归</span><strong>{memoryBaseline?.value}</strong><small>{memoryBaseline?.detail}</small></div>
  </section>;
}
