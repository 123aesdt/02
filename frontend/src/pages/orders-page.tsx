import { ChevronRight, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { DataTable, type DataTableColumn } from "../components/ui/data-table";
import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";
import { Drawer, Metric } from "../components/workspace-ui";
import { runtimeConfig } from "../config/runtime";
import { useOrdersRead } from "../hooks/use-workspace-reads";
import { useOrders } from "../hooks/use-workspace-data";
import type { OrderRecord } from "../mocks/workspace-data";
import type { OrderListItem, WorkspaceReadProvenance } from "../types/workspace-read-models";
import { localizeStatus } from "../utils/presentation-labels";

function provenanceLabel(provenance: WorkspaceReadProvenance) { return provenance === "LIVE" ? "实时数据" : provenance === "MIXED" ? "混合数据" : "演示数据"; }

function OrderReadFeedback({ state, onRetry }: { state: string; onRetry: () => void }) {
  if (state === "LOADING") return <Skeleton label="正在加载运单记录" lines={5} />;
  if (state === "EMPTY") return <EmptyState kind="empty" title="当前没有运单记录" description="筛选范围内暂无运单。" />;
  if (state === "FORBIDDEN") return <EmptyState kind="forbidden" title="没有查看运单记录的权限" />;
  if (state === "UNAVAILABLE") return <EmptyState kind="unavailable" title="服务暂不可用" description="请稍后重试。" action={<button type="button" onClick={onRetry}>重试</button>} />;
  return <EmptyState kind="error" title="运单记录加载失败" description="请重试后再查看。" action={<button type="button" onClick={onRetry}>重试</button>} />;
}

function MockOrdersPage() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<OrderRecord | null>(null);
  const filters = useMemo(() => ({ query, status }), [query, status]);
  const records = useOrders(filters);

  return <div className="workspace-page"><section className="metrics-grid workspace-metrics"><Metric label="今日运单" value="1,284" note="较昨日 +8.4%" /><Metric label="配送中" value="863" note="67.2% 正在执行" tone="teal" /><Metric label="准时配送率" value="96.8%" note="目标 95.0%" tone="teal" /><Metric label="异常关联" value="17" note="当前自动决策中" tone="amber" /></section><section className="workspace-panel"><div className="panel-heading"><div><p className="eyebrow">运单运营</p><h2>运单管理</h2></div><span className="panel-note">演示数据</span></div><div className="filters"><label><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="运单 / 客户 / 司机 / 车辆" /></label><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">全部状态</option><option>已完成调度</option><option>处理中</option><option>人工复核</option><option>已降级</option></select></div><div className="table-wrap"><table><thead><tr><th>运单号</th><th>客户</th><th>司机</th><th>车辆</th><th>路线</th><th>预计送达</th><th>状态</th><th>更新</th><th /></tr></thead><tbody>{records.map((item) => <tr key={item.orderId} className={item.orderId.endsWith("00128") ? "featured-row" : ""}><td><button className="table-link inline-link" onClick={() => setSelected(item)}>{item.orderId}</button></td><td>{item.customer}</td><td>{item.driver}</td><td>{item.vehicle}</td><td>{item.route}</td><td>{item.eta}</td><td><span className="table-status">{item.status}</span></td><td>{item.updatedAt}</td><td><button className="row-action" aria-label={`查看 ${item.orderId}`} onClick={() => setSelected(item)}><ChevronRight size={16} /></button></td></tr>)}</tbody></table></div></section><Drawer title={selected?.orderId ?? "运单详情"} open={Boolean(selected)} onClose={() => setSelected(null)}>{selected ? <div className="drawer-content"><div className="timeline"><span><i />订单创建 · 17:20</span><span><i />司机接单 · 18:02</span><span><i className="amber" />异常识别 · {selected.updatedAt}</span><span><i />AI 调度完成 · 已持久化</span></div><div className="detail-list"><span>客户<strong>{selected.customer}</strong></span><span>司机<strong>{selected.driver}</strong></span><span>任务<strong>{selected.taskId}</strong></span></div><Link className="button-primary drawer-link" to={`/dispatch/${selected.taskId}`}>查看关联调度 <ChevronRight size={15} /></Link></div> : null}</Drawer></div>;
}

function ApiOrdersPage() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [history, setHistory] = useState<(string | null)[]>([]);
  const [selected, setSelected] = useState<OrderListItem | null>(null);
  const read = useOrdersRead({ query, status, cursor });
  const reset = () => { setCursor(null); setHistory([]); };
  const controls = <div className="filters"><label><Search size={15}/><input value={query} onChange={(event) => { setQuery(event.target.value); reset(); }} placeholder="运单 / 司机 / 车辆"/></label><select value={status} onChange={(event) => { setStatus(event.target.value); reset(); }}><option value="">全部状态</option><option value="PENDING">等待中</option><option value="RUNNING">运行中</option><option value="PROCESSING">处理中</option><option value="COMPLETED">已完成</option></select></div>;
  if (read.state !== "READY") return <div className="workspace-page"><section className="workspace-panel"><div className="panel-heading"><div><p className="eyebrow">运单运营</p><h2>运单管理</h2></div><span className="source-label live">API</span></div>{controls}<OrderReadFeedback state={read.state} onRetry={read.refresh} />{history.length ? <div><button type="button" onClick={() => { const previous = history.at(-1) ?? null; setHistory((items) => items.slice(0, -1)); setCursor(previous); }}>上一页</button><button type="button" onClick={reset}>返回首页</button></div> : null}</section></div>;
  const columns: DataTableColumn<OrderListItem>[] = [{ key: "order_no", label: "运单号", render: (item) => <button className="table-link inline-link" onClick={() => setSelected(item)}>{item.order_no}</button> }, { key: "status", label: "状态", render: (item) => localizeStatus(item.status) }, { key: "driver_id", label: "司机" }, { key: "vehicle_id", label: "车辆" }, { key: "route_id", label: "路线" }, { key: "origin", label: "起点" }, { key: "destination", label: "终点" }, { key: "anomaly_count", label: "异常数" }, { key: "updated_at", label: "更新时间" }];
  return <div className="workspace-page"><section className="metrics-grid workspace-metrics"><Metric label="当前运单" value={String(read.data.total)} note="接口返回总数"/></section><section className="workspace-panel"><div className="panel-heading"><div><p className="eyebrow">运单运营</p><h2>运单管理</h2></div><span className={`source-label ${read.data.provenance === "LIVE" ? "live" : "demo"}`}>{provenanceLabel(read.data.provenance)}</span></div>{controls}<DataTable caption="运单记录" columns={columns} rows={read.data.items} rowKey={(item) => String(item.row_id)} />{read.data.next_cursor ? <button type="button" onClick={() => { setHistory((items) => [...items, cursor]); setCursor(read.data.next_cursor); }}>下一页</button> : null}{history.length ? <div><button type="button" onClick={() => { const previous = history.at(-1) ?? null; setHistory((items) => items.slice(0, -1)); setCursor(previous); }}>上一页</button><button type="button" onClick={reset}>返回首页</button></div> : null}</section><Drawer title={selected?.order_no ?? "运单详情"} open={Boolean(selected)} onClose={() => setSelected(null)}>{selected ? <div className="drawer-content"><div className="detail-list"><span>状态<strong>{localizeStatus(selected.status)}</strong></span><span>司机<strong>{selected.driver_id ?? "—"}</strong></span><span>车辆<strong>{selected.vehicle_id ?? "—"}</strong></span><span>路线<strong>{selected.route_id ?? "—"}</strong></span><span>起点<strong>{selected.origin}</strong></span><span>终点<strong>{selected.destination}</strong></span><span>关联异常<strong>{selected.anomaly_count}</strong></span><span>创建时间<strong>{selected.created_at}</strong></span><span>更新时间<strong>{selected.updated_at}</strong></span></div>{selected.latest_task_id ? <Link className="button-primary drawer-link" to={`/dispatch/${selected.latest_task_id}`}>查看关联调度 <ChevronRight size={15}/></Link> : null}</div> : null}</Drawer></div>;
}

export function OrdersPage() { return runtimeConfig.dataMode === "api" ? <ApiOrdersPage /> : <MockOrdersPage />; }
