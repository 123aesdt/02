import { ChevronRight, Filter, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { DataTable, type DataTableColumn } from "../components/ui/data-table";
import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";
import { Drawer, Metric, RiskLabel } from "../components/workspace-ui";
import { runtimeConfig } from "../config/runtime";
import { useAnomaliesRead } from "../hooks/use-workspace-reads";
import { useAnomalies } from "../hooks/use-workspace-data";
import type { AnomalyRecord, Risk } from "../mocks/workspace-data";
import type { AnomalyListItem, WorkspaceReadProvenance } from "../types/workspace-read-models";
import { localizeStatus } from "../utils/presentation-labels";

function provenanceLabel(provenance: WorkspaceReadProvenance) {
  return provenance === "LIVE" ? "实时数据" : provenance === "MIXED" ? "混合数据" : "演示数据";
}

function AnomalyReadFeedback({ state, onRetry }: { state: string; onRetry: () => void }) {
  if (state === "LOADING") return <Skeleton label="正在加载异常记录" lines={5} />;
  if (state === "EMPTY") return <EmptyState kind="empty" title="当前没有异常记录" description="筛选范围内暂无异常。" />;
  if (state === "FORBIDDEN") return <EmptyState kind="forbidden" title="没有查看异常记录的权限" />;
  if (state === "UNAVAILABLE") return <EmptyState kind="unavailable" title="服务暂不可用" description="请稍后重试。" action={<button type="button" onClick={onRetry}>重试</button>} />;
  return <EmptyState kind="error" title="异常记录加载失败" description="请重试后再查看。" action={<button type="button" onClick={onRetry}>重试</button>} />;
}

function MockAnomaliesPage() {
  const [query, setQuery] = useState("");
  const [risk, setRisk] = useState<Risk | "">("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<AnomalyRecord | null>(null);
  const filters = useMemo(() => ({ query, risk, type, status }), [query, risk, type, status]);
  const records = useAnomalies(filters);

  const closeDrawer = () => setSelected(null);

  return <div className="workspace-page"><section className="metrics-grid workspace-metrics"><Metric label="当前异常" value="17" note="实时追踪县域配送异常" tone="amber"/><Metric label="高风险" value="4" note="含 2 个道路事件" tone="amber"/><Metric label="AI 自动处理" value="11" note="近 7 日平均" tone="teal"/><Metric label="人工复核" value="2" note="等待运营确认" tone="violet"/></section><section className="workspace-panel"><div className="panel-heading"><div><p className="eyebrow">异常工作台</p><h2>异常中心</h2></div><span className="panel-note">演示数据 · {records.length} 条结果</span></div><div className="filters"><label><Search size={15}/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="异常号 / 运单 / 司机"/></label><select value={type} onChange={(event) => setType(event.target.value)}><option value="">全部异常类型</option>{["暴雨道路湿滑", "道路封闭", "车辆故障", "站点积压", "运力不足", "天气预警"].map((value) => <option key={value}>{value}</option>)}</select><select value={risk} onChange={(event) => setRisk(event.target.value as Risk | "")}><option value="">全部风险</option><option value="HIGH">高</option><option value="MEDIUM">中</option><option value="LOW">低</option></select><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">全部 AI 状态</option><option>已完成调度</option><option>处理中</option><option>人工复核</option><option>已降级</option></select><Filter size={16}/></div><div className="table-wrap"><table><thead><tr><th>异常编号</th><th>运单</th><th>异常类型</th><th>风险</th><th>司机 / 车辆</th><th>当前路线</th><th>AI 状态</th><th>发生时间</th><th>处理耗时</th><th/></tr></thead><tbody>{records.map((item) => <tr key={item.id} className={item.id === "ANM-20260821-017" ? "featured-row" : ""}><td><button className="table-link inline-link" onClick={() => setSelected(item)}>{item.id}</button></td><td>{item.orderId}</td><td>{item.type}</td><td><RiskLabel value={item.risk}/></td><td>{item.driver} <small className="muted">{item.vehicle}</small></td><td>{item.route}</td><td><span className="table-status">{item.status}</span></td><td>{item.occurredAt}</td><td>2 分 14 秒</td><td><button className="row-action" aria-label={`查看 ${item.id}`} onClick={() => setSelected(item)}><ChevronRight size={16}/></button></td></tr>)}</tbody></table></div></section><Drawer title={selected?.id ?? "异常详情"} open={Boolean(selected)} onClose={closeDrawer}>{selected && <div className="drawer-content"><p className="description">{selected.description}</p><div className="detail-list"><span>运单<strong>{selected.orderId}</strong></span><span>司机<strong>{selected.driver}</strong></span><span>车辆<strong>{selected.vehicle}</strong></span><span>原路线<strong>{selected.route}</strong></span><span>风险<strong>{localizeStatus(selected.risk)}</strong></span><span>AI 当前阶段<strong>{selected.status}</strong></span><span>环境<strong>雨天湿滑 · 已降级</strong></span><span>记忆<strong>memory-rain-li</strong></span><span>推荐路线<strong>national-102</strong></span><span>最终状态<strong>{localizeStatus("APPROVED")}</strong></span></div><Link className="button-primary drawer-link" to={`/dispatch/${selected.taskId}`}>打开智能调度详情 <ChevronRight size={15}/></Link></div>}</Drawer></div>;
}

function ApiAnomaliesPage() {
  const [query, setQuery] = useState("");
  const [risk, setRisk] = useState<Risk | "">("");
  const [status, setStatus] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [history, setHistory] = useState<(string | null)[]>([]);
  const [selected, setSelected] = useState<AnomalyListItem | null>(null);
  const read = useAnomaliesRead({ query, risk, status, cursor });
  const reset = () => { setCursor(null); setHistory([]); };
  const controls = <div className="filters"><label><Search size={15}/><input value={query} onChange={(event) => { setQuery(event.target.value); reset(); }} placeholder="异常号 / 运单"/></label><select value={risk} onChange={(event) => { setRisk(event.target.value as Risk | ""); reset(); }}><option value="">全部风险</option><option value="HIGH">高</option><option value="MEDIUM">中</option><option value="LOW">低</option></select><select value={status} onChange={(event) => { setStatus(event.target.value); reset(); }}><option value="">全部状态</option><option value="PENDING">等待中</option><option value="PROCESSING">处理中</option><option value="RUNNING">运行中</option><option value="COMPLETED">已完成</option></select><Filter size={16}/></div>;
  if (read.state !== "READY") return <div className="workspace-page"><section className="workspace-panel"><div className="panel-heading"><div><p className="eyebrow">异常工作台</p><h2>异常中心</h2></div><span className="source-label live">API</span></div>{controls}<AnomalyReadFeedback state={read.state} onRetry={read.refresh} />{history.length ? <div><button type="button" onClick={() => { const previous = history.at(-1) ?? null; setHistory((items) => items.slice(0, -1)); setCursor(previous); }}>上一页</button><button type="button" onClick={reset}>返回首页</button></div> : null}</section></div>;
  const columns: DataTableColumn<AnomalyListItem>[] = [{ key: "anomaly_no", label: "异常编号", render: (item) => <button className="table-link inline-link" onClick={() => setSelected(item)}>{item.anomaly_no}</button> }, { key: "order_no", label: "运单" }, { key: "anomaly_type", label: "异常类型" }, { key: "risk", label: "风险", render: (item) => <RiskLabel value={item.risk} /> }, { key: "driver_id", label: "司机" }, { key: "vehicle_id", label: "车辆" }, { key: "route_id", label: "路线" }, { key: "status", label: "状态", render: (item) => localizeStatus(item.status) }, { key: "reported_at", label: "发生时间" }];
  const highRisk = read.data.items.filter((item) => item.risk.toUpperCase() === "HIGH").length;
  return <div className="workspace-page"><section className="metrics-grid workspace-metrics"><Metric label="当前异常" value={String(read.data.total)} note="接口返回总数" tone="amber"/><Metric label="本页高风险" value={String(highRisk)} note="由本页记录派生" tone="amber"/></section><section className="workspace-panel"><div className="panel-heading"><div><p className="eyebrow">异常工作台</p><h2>异常中心</h2></div><span className={`source-label ${read.data.provenance === "LIVE" ? "live" : "demo"}`}>{provenanceLabel(read.data.provenance)}</span></div>{controls}<DataTable caption="异常记录" columns={columns} rows={read.data.items} rowKey={(item) => String(item.row_id)} />{read.data.next_cursor ? <button type="button" onClick={() => { setHistory((items) => [...items, cursor]); setCursor(read.data.next_cursor); }}>下一页</button> : null}{history.length ? <div><button type="button" onClick={() => { const previous = history.at(-1) ?? null; setHistory((items) => items.slice(0, -1)); setCursor(previous); }}>上一页</button><button type="button" onClick={reset}>返回首页</button></div> : null}</section><Drawer title={selected?.anomaly_no ?? "异常详情"} open={Boolean(selected)} onClose={() => setSelected(null)}>{selected ? <div className="drawer-content"><p>{selected.description}</p><div className="detail-list"><span>运单<strong>{selected.order_no ?? "—"}</strong></span><span>司机<strong>{selected.driver_id ?? "—"}</strong></span><span>车辆<strong>{selected.vehicle_id ?? "—"}</strong></span><span>路线<strong>{selected.route_id ?? "—"}</strong></span><span>异常类型<strong>{selected.anomaly_type}</strong></span><span>风险<strong>{localizeStatus(selected.risk)}</strong></span><span>状态<strong>{localizeStatus(selected.status)}</strong></span><span>发生时间<strong>{selected.reported_at}</strong></span></div>{selected.latest_task_id ? <Link className="button-primary drawer-link" to={`/dispatch/${selected.latest_task_id}`}>打开智能调度详情 <ChevronRight size={15}/></Link> : null}</div> : null}</Drawer></div>;
}

export function AnomaliesPage() { return runtimeConfig.dataMode === "api" ? <ApiAnomaliesPage /> : <MockAnomaliesPage />; }
