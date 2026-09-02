import { ArrowRight, ChevronRight, Database, Gauge, RadioTower, Server } from "lucide-react";
import { Link } from "react-router-dom";

import { AgentPipeline } from "../components/agent-pipeline";
import { RouteVisual } from "../components/route-visual";
import { useDashboardData } from "../hooks/use-dispatch-data";
import { DispatchSubmissionButton } from "../components/dispatch-submission-button";
import { V2CapabilitySummary } from "../components/v2-capability-summary";
import { runtimeConfig } from "../config/runtime";
import { localizeStatus } from "../utils/presentation-labels";

export function DashboardPage() {
  const data = useDashboardData();
  if (!data && runtimeConfig.dataMode === "mock") return <div className="loading-state">正在载入运营数据…</div>;
  if (!data) return <div className="dashboard-page"><V2CapabilitySummary/><section className="workspace-panel api-empty-state"><p className="eyebrow">实时 API 模式</p><h2>业务汇总接口未开放</h2><p>当前页面不会回退演示数据。请从智能调度、记忆中心或系统监控进入已有真实 API / WebSocket 工作流。</p></section></div>;
  return <div className="dashboard-page"><V2CapabilitySummary/><div className="dashboard-command"><div><p className="eyebrow">核心异常 · 李师傅 / 新平路 · 演示数据</p><h2>暴雨道路湿滑</h2></div><DispatchSubmissionButton/></div><section className="metrics-grid">{data.metrics.map((metric) => <article className={`metric ${metric.tone ?? ""}`} key={metric.label}><p>{metric.label}</p><strong>{metric.value}</strong><span>{metric.note} · 演示数据</span></article>)}</section>
    <section className="dashboard-main"><article className="situation-panel"><div className="panel-heading"><div><p className="eyebrow">县域运营态势</p><h2>县域物流运行态势</h2></div><span className="source-label demo">演示数据</span></div><RouteVisual/><div className="route-legend"><span><i className="legend-origin"/>中心仓与站点</span><span><i className="legend-danger"/>原路线风险</span><span><i className="legend-teal"/>AI 推荐路线</span></div></article><aside className="system-metrics"><div className="panel-heading"><div><p className="eyebrow">演示态势</p><h2>非实时指标</h2></div><RadioTower size={18}/></div><div className="system-stat"><span>演示请求数</span><strong>428</strong><svg viewBox="0 0 110 28"><path d="M0 22 L13 19 L24 22 L37 9 L50 16 L63 8 L78 13 L91 3 L110 8"/></svg></div><div className="system-stat"><span>演示响应</span><strong>184<small>毫秒</small></strong><svg viewBox="0 0 110 28"><path d="M0 15 L13 20 L25 10 L39 14 L53 8 L66 13 L80 5 L95 12 L110 7"/></svg></div><div className="health-grid"><span><Database size={15}/>Redis <b>演示</b></span><span><Server size={15}/>Worker <b>演示</b></span><span><Gauge size={15}/>错误 <b>演示</b></span></div></aside></section>
    <section className="dashboard-lower"><article className="anomaly-table-panel"><div className="panel-heading"><div><p className="eyebrow">异常工作台</p><h2>最近异常</h2></div><Link to="/anomalies" className="text-action">查看全部 <ArrowRight size={14}/></Link></div><div className="table-wrap"><table><thead><tr><th>异常编号</th><th>运单</th><th>异常类型</th><th>风险</th><th>司机</th><th>当前路线</th><th>AI 状态</th><th>发生时间</th><th/></tr></thead><tbody>{data.recentAnomalies.map((row) => <tr key={row.id} className={row.taskId === "TASK-20260821-0042" ? "featured-row" : ""}><td><Link to={`/dispatch/${row.taskId}`} className="table-link">{row.id}</Link></td><td>{row.orderId}</td><td>{row.type}</td><td><span className={`risk risk-${row.risk.toLowerCase()}`}>{localizeStatus(row.risk)}</span></td><td>{row.driver}</td><td>{row.route}</td><td><span className="table-status">{row.status}</span></td><td>{row.occurredAt}</td><td><Link to={`/dispatch/${row.taskId}`} aria-label={`查看 ${row.id}`}><ChevronRight size={16}/></Link></td></tr>)}</tbody></table></div></article><AgentPipeline agents={data.agents}/></section>
  </div>;
}
