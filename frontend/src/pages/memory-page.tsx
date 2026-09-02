import { ChevronRight, Database, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { GraphMemoryView } from "../components/graph-memory-view";
import { SharedMemoryControl } from "../components/shared-memory-control";
import { DataTable, type DataTableColumn } from "../components/ui/data-table";
import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";
import { Drawer, Metric } from "../components/workspace-ui";
import { runtimeConfig } from "../config/runtime";
import { useGraphMemoryEvents } from "../hooks/use-graph-memory-events";
import { useVectorMemoriesRead } from "../hooks/use-workspace-reads";
import { useMemories, useMemoryControlPlane } from "../hooks/use-workspace-data";
import { demoGraphMemory, demoSharedMemoryFact } from "../mocks/v2-product-data";
import type { MemoryRecord } from "../mocks/workspace-data";
import type { VectorMemoryListItem, WorkspaceReadProvenance } from "../types/workspace-read-models";
import { localizeStatus } from "../utils/presentation-labels";
import "../styles/memory-control.css";

type MemoryTab = "vector" | "graph" | "shared";

export interface MemoryPageProps { controlFactKey?: string; }

function provenanceLabel(provenance: WorkspaceReadProvenance) {
  return provenance === "LIVE" ? "实时数据" : provenance === "MIXED" ? "混合数据" : "演示数据";
}

function MemoryTabs({ tab, onChange, mode }: { tab: MemoryTab; onChange: (tab: MemoryTab) => void; mode: "api" | "mock" }) {
  const layer = tab === "vector" ? "Qdrant · 语义长期记忆" : tab === "graph" ? "Neo4j · 关系长期记忆" : "MySQL · 规范控制平面";
  const source = mode === "mock" ? "演示数据" : tab === "graph" ? "实时事件" : "实时 API";
  return <section className="memory-tab-shell">
    <div role="tablist" aria-label="记忆层" className="memory-tabs">
      {(["vector", "graph", "shared"] as const).map((id) => <button type="button" role="tab" aria-selected={tab === id} key={id} className={tab === id ? "selected" : ""} onClick={() => onChange(id)}>{id === "vector" ? "向量记忆" : id === "graph" ? "图记忆" : "共享控制"}</button>)}
    </div>
    <div className="memory-layer-copy"><strong>{layer}</strong><span className={`source-label ${mode === "mock" ? "demo" : "live"}`}>{source}</span></div>
  </section>;
}

function MockVectorMemorySurface() {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<MemoryRecord | null>(null);
  const records = useMemories(query);
  return <>
    <section className="metrics-grid workspace-metrics"><Metric label="向量 Top-1" value="49 / 50 · 98%" note="已通过验收" tone="violet"/><Metric label="向量 Top-3" value="50 / 50 · 100%" note="已通过验收" tone="teal"/><Metric label="向量维度" value="2560" note="Qwen3-Embedding-4B 维度"/><Metric label="服务商" value="SiliconFlow" note="最新 V2-E 证据"/></section>
    <section className="workspace-panel"><div className="panel-heading"><div><p className="eyebrow">QDRANT 向量记忆</p><h2>向量记忆</h2></div><span className="source-label demo">演示数据</span></div><div className="filters"><label><Search size={15}/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="记忆 ID / 实体 / 场景 / 解决方案"/></label><select aria-label="向量关系筛选"><option>全部实体关系</option><option>司机 → 路线</option><option>路线 → 解决方案</option></select></div><div className="table-wrap"><table><thead><tr><th>记忆 ID</th><th>司机 / 路线</th><th>异常</th><th>历史解决方案</th><th>相似度</th><th>维度</th><th>状态</th><th>更新</th><th/></tr></thead><tbody>{records.map((item) => <tr key={item.memoryId} className={item.memoryId === "memory-rain-li" ? "featured-row" : ""}><td><button className="table-link inline-link" onClick={() => setSelected(item)}>{item.memoryId}</button></td><td>{item.entities}</td><td>{item.scenario}</td><td className="memory-resolution">{item.resolution}</td><td>{item.similarity}</td><td>{item.vectorDimension}</td><td><span className="table-status">已生效</span></td><td>{item.updatedAt}</td><td><button aria-label={`查看 ${item.memoryId}`} className="row-action" onClick={() => setSelected(item)}><ChevronRight size={16}/></button></td></tr>)}</tbody></table></div></section>
    <Drawer title={selected?.memoryId ?? "记忆详情"} open={Boolean(selected)} onClose={() => setSelected(null)}>{selected ? <div className="drawer-content"><div className="relation-graph"><span>李师傅</span><i/><span>新平路</span><i/><span className="danger">雨天道路湿滑</span><i/><span className="success">建议改走102国道</span></div><div className="detail-list"><span>向量<strong>{selected.vectorDimension} 维</strong></span><span>相似度<strong>{selected.similarity}</strong></span><span>嵌入状态<strong>已生效</strong></span><span>最近采纳<strong>{selected.adoptedBy}</strong></span></div><div className="drawer-callout"><Database size={16}/>Qdrant 余弦 Top-K → 记忆召回</div><Link className="button-primary drawer-link" to="/dispatch/TASK-20260821-0042">查看关联调度证据 <ChevronRight size={15}/></Link></div> : null}</Drawer>
  </>;
}

function VectorMemoryFeedback({ state, hasHistory, onRetry }: { state: string; hasHistory: boolean; onRetry: () => void }) {
  if (state === "LOADING") return <Skeleton label="正在加载向量记忆" lines={5} />;
  if (state === "EMPTY") return <EmptyState kind="empty" title={hasHistory ? "当前页没有向量记忆" : "当前没有向量记忆"} description={hasHistory ? "可返回上一页或首页继续浏览。" : "Qdrant 集合当前没有可浏览记录。"} />;
  if (state === "FORBIDDEN") return <EmptyState kind="forbidden" title="没有查看向量记忆的权限" />;
  if (state === "UNAVAILABLE") return <EmptyState kind="unavailable" title="向量记忆服务暂不可用" description="请稍后重试。" action={<button type="button" onClick={onRetry}>重试</button>} />;
  return <EmptyState kind="error" title="向量记忆加载失败" description="请重试后再查看。" action={<button type="button" onClick={onRetry}>重试</button>} />;
}

function ApiVectorMemorySurface() {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [history, setHistory] = useState<(string | null)[]>([]);
  const [selected, setSelected] = useState<VectorMemoryListItem | null>(null);
  const read = useVectorMemoriesRead({ limit: 20, cursor });
  const rows = useMemo(() => {
    if (read.state !== "READY") return [];
    const normalizedQuery = query.trim().toLocaleLowerCase("zh-CN");
    if (!normalizedQuery) return read.data.items;
    return read.data.items.filter((item) => [item.memory_id, item.driver_id, item.route_id, item.anomaly_type, item.historical_resolution, item.created_at, item.projection_status]
      .filter((value): value is string => Boolean(value))
      .some((value) => value.toLocaleLowerCase("zh-CN").includes(normalizedQuery)));
  }, [query, read]);
  const reset = () => { setCursor(null); setHistory([]); };
  const previous = () => { const previousCursor = history.at(-1) ?? null; setHistory((items) => items.slice(0, -1)); setCursor(previousCursor); };
  const pagination = history.length ? <div><button type="button" onClick={previous}>上一页</button><button type="button" onClick={reset}>返回首页</button></div> : null;
  const controls = <div className="filters"><label><Search size={15}/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="记忆 ID / 司机 / 路线 / 异常 / 解决方案"/></label></div>;
  const columns: DataTableColumn<VectorMemoryListItem>[] = [
    { key: "memory_id", label: "记忆 ID", render: (item) => <button type="button" className="table-link inline-link" onClick={() => setSelected(item)}>{item.memory_id ?? "未标记"}</button> },
    { key: "driver_id", label: "司机" },
    { key: "route_id", label: "路线" },
    { key: "anomaly_type", label: "异常类型" },
    { key: "historical_resolution", label: "历史解决方案" },
    { key: "projection_status", label: "投影状态", render: (item) => localizeStatus(item.projection_status ?? "—") },
    { key: "created_at", label: "创建时间" },
  ];
  const emptyRows = read.state === "READY" && read.data.items.length === 0
    ? <EmptyState kind="empty" title={history.length ? "当前页没有向量记忆" : "当前没有向量记忆"} description={history.length ? "可返回上一页或首页继续浏览。" : "Qdrant 集合当前没有可浏览记录。"} />
    : <EmptyState kind="empty" title="当前筛选没有匹配的向量记忆" />;

  return <>
    {read.state === "READY" ? <section className="metrics-grid workspace-metrics"><Metric label="记忆总数" value={String(read.data.total)} note="接口返回集合记录总数" tone="teal"/><Metric label="向量维度" value={read.data.vector_dimension == null ? "—" : String(read.data.vector_dimension)} note="Qdrant 当前集合配置" tone="violet"/></section> : null}
    <section className="workspace-panel"><div className="panel-heading"><div><p className="eyebrow">QDRANT 向量记忆</p><h2>向量记忆</h2></div><span className={`source-label ${read.state === "READY" && read.data.provenance === "LIVE" ? "live" : "demo"}`}>{read.state === "READY" ? provenanceLabel(read.data.provenance) : "实时 API"}</span></div>{controls}{read.state === "READY" ? <><DataTable caption="向量记忆记录" columns={columns} rows={rows} rowKey={(item, index) => item.memory_id ?? `memory-${index}`} empty={emptyRows}/>{read.data.next_cursor ? <button type="button" onClick={() => { setHistory((items) => [...items, cursor]); setCursor(read.data.next_cursor); }}>下一页</button> : null}{pagination}</> : <><VectorMemoryFeedback state={read.state} hasHistory={history.length > 0} onRetry={read.refresh}/>{pagination}</>}</section>
    <Drawer title="向量记忆详情" open={Boolean(selected)} onClose={() => setSelected(null)}>{selected ? <div className="drawer-content"><div className="detail-list"><span>记忆 ID<strong>{selected.memory_id ?? "—"}</strong></span><span>司机<strong>{selected.driver_id ?? "—"}</strong></span><span>路线<strong>{selected.route_id ?? "—"}</strong></span><span>异常类型<strong>{selected.anomaly_type ?? "—"}</strong></span><span>历史解决方案<strong>{selected.historical_resolution ?? "—"}</strong></span><span>创建时间<strong>{selected.created_at ?? "—"}</strong></span><span>投影状态<strong>{localizeStatus(selected.projection_status ?? "—")}</strong></span></div><div className="drawer-callout"><Database size={16}/>Qdrant 安全元数据 · 不包含向量值</div></div> : null}</Drawer>
  </>;
}

function MockGraphMemorySurface() {
  const graph = useGraphMemoryEvents("");
  return <GraphMemoryView graph={graph.graph}/>;
}

function ApiGraphMemorySurface({ taskId, onTaskIdChange }: { taskId: string; onTaskIdChange: (taskId: string) => void }) {
  const graph = useGraphMemoryEvents(taskId);
  const hasLiveEvidence = graph.graph.entities.length > 0 || graph.graph.relations.length > 0 || graph.graph.paths.length > 0;
  return <><section className="workspace-panel graph-task-query"><div className="panel-heading"><div><p className="eyebrow">任务事件历史</p><h2>加载真实图记忆证据</h2></div><span>{graph.connection}</span></div><label>任务 ID<input value={taskId} onChange={(event) => onTaskIdChange(event.target.value)} placeholder="TASK-..."/></label>{!hasLiveEvidence ? <p>当前暂无真实图事件，以下展示已标注的演示数据；输入任务 ID 后将自动切换为真实证据。</p> : null}</section><GraphMemoryView graph={hasLiveEvidence ? graph.graph : demoGraphMemory}/></>;
}

function ApiSharedMemorySurface({ factKey, onFactKeyChange }: { factKey: string; onFactKeyChange: (factKey: string) => void }) {
  const control = useMemoryControlPlane(factKey);
  const showDemo = !control.loading && !control.data;
  return <SharedMemoryControl
    factKey={factKey}
    onFactKeyChange={onFactKeyChange}
    data={showDemo ? demoSharedMemoryFact : control.data}
    loading={control.loading}
    error={control.error}
    demo={showDemo}
  />;
}

function MockMemoryPage({ controlFactKey }: { controlFactKey: string }) {
  const [tab, setTab] = useState<MemoryTab>(controlFactKey ? "shared" : "vector");
  const [factKey, setFactKey] = useState(controlFactKey);
  return <div className="workspace-page memory-page-v2"><MemoryTabs tab={tab} onChange={setTab} mode="mock"/>{tab === "vector" ? <MockVectorMemorySurface/> : null}{tab === "graph" ? <MockGraphMemorySurface/> : null}{tab === "shared" ? <SharedMemoryControl factKey={factKey} onFactKeyChange={setFactKey} data={demoSharedMemoryFact} loading={false} error={null} demo/> : null}</div>;
}

function ApiMemoryPage({ controlFactKey }: { controlFactKey: string }) {
  const [tab, setTab] = useState<MemoryTab>(controlFactKey ? "shared" : "vector");
  const [taskId, setTaskId] = useState("");
  const [factKey, setFactKey] = useState(controlFactKey);
  return <div className="workspace-page memory-page-v2"><MemoryTabs tab={tab} onChange={setTab} mode="api"/>{tab === "vector" ? <ApiVectorMemorySurface/> : null}{tab === "graph" ? <ApiGraphMemorySurface taskId={taskId} onTaskIdChange={setTaskId}/> : null}{tab === "shared" ? <ApiSharedMemorySurface factKey={factKey} onFactKeyChange={setFactKey}/> : null}</div>;
}

export function MemoryPage({ controlFactKey = "" }: MemoryPageProps) {
  return runtimeConfig.dataMode === "api" ? <ApiMemoryPage controlFactKey={controlFactKey}/> : <MockMemoryPage controlFactKey={controlFactKey}/>;
}
