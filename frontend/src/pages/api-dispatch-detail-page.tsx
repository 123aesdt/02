import { CircleAlert, Route as RouteIcon, ShieldCheck } from "lucide-react";
import { useCallback, useState } from "react";
import { Link } from "react-router-dom";

import { useHasPermission } from "../auth/auth-state";
import { PERMISSIONS } from "../auth/permissions";
import { AgentPipeline } from "../components/agent-pipeline";
import { AuditEvidencePanel } from "../components/audit-evidence-panel";
import { DispatchEvidenceOverview } from "../components/dispatch-evidence-overview";
import { FleetAllocationPanel } from "../components/fleet-allocation-panel";
import { LiveVehicleMap } from "../components/live-vehicle-map";
import { PublishedAmapRouteMap } from "../components/published-amap-route-map";
import { RoutePlanResultPanel } from "../components/route-plan-result-panel";
import { RoutingEvidencePanel } from "../components/routing-evidence-panel";
import { RuntimeWorkbench } from "../components/runtime-workbench";
import { StatusPill } from "../components/status-pill";
import { VehicleOperationDispatchPanel } from "../components/vehicle-operation-dispatch-panel";
import { runtimeConfig } from "../config/runtime";
import { resolveEvidenceScenario } from "../features/dispatch/evidence-scenario";
import { taskStateCopy } from "../features/dispatch/task-state";
import { useTaskApi } from "../hooks/use-task-api";
import { useTaskEvents } from "../hooks/use-task-events";
import { ApiError } from "../services/api/client";
import { publishDispatchTask, type DispatchPublicationResponse } from "../services/dispatch-service";
import type { RuntimeOverrideHistory } from "../types/runtime-override";
import { localizeDisplayText, localizeEntityType, localizeField, localizeRelationType, localizeStatus } from "../utils/presentation-labels";

const EVENT_FIELD_LABELS: Record<string, string> = {
  memory_id: "记忆 ID", score: "评分", recommendation: "建议", resolution: "解决方案", evidence: "证据", matched: "已匹配",
  fallback_reason: "降级原因", environment_elapsed_ms: "环境耗时（毫秒）", environment_risk: "环境风险",
  recommended_route: "推荐路线", decision: "决策", memory_adopted: "已采纳记忆", adopted_memory_id: "已采纳记忆 ID",
  status: "状态", executed: "已执行", version: "版本", route: "路线", manual_review: "人工复核",
  result: "结果", reason: "原因", checks: "检查项",
};

function DetailRow({ label, value }: { label: string; value: string }) {
  return <div className="detail-row"><span>{label}</span><strong>{value}</strong></div>;
}

function displayEventValue(value: unknown): string {
  if (value === undefined || value === null) return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "string") return localizeDisplayText(localizeStatus(value));
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function EventData({ label, data, fields }: { label: string; data: Record<string, unknown> | undefined; fields: string[] }) {
  return <section className="dispatch-result"><p className="eyebrow">{label}</p>{fields.map((field) => <DetailRow key={field} label={EVENT_FIELD_LABELS[field] ?? field} value={displayEventValue(data?.[field])}/>)}</section>;
}

function graphEntityName(value: unknown): string {
  if (!value || typeof value !== "object") return "—";
  const entity = value as Record<string, unknown>;
  return String(entity.display_name ?? entity.entity_id ?? "—");
}

function GraphMemoryEventData({ data }: { data: Record<string, unknown> | undefined }) {
  const facts = Array.isArray(data?.graph_memory_facts) ? data.graph_memory_facts : [];
  const paths = Array.isArray(data?.graph_memory_paths) ? data.graph_memory_paths : [];
  const factText = facts.map((value) => {
    const fact = value as Record<string, unknown>;
    return `${graphEntityName(fact.source)} → ${localizeRelationType(String(fact.relation_type ?? "—"))} → ${graphEntityName(fact.target)}`;
  }).join("；");
  const pathText = paths.map((value) => {
    const path = value as Record<string, unknown>;
    return Array.isArray(path.entities) ? path.entities.map(graphEntityName).join(" → ") : "—";
  }).join("；");
  return <section className="dispatch-result"><p className="eyebrow">图记忆事件</p><DetailRow label="已使用" value={data?.graph_memory_used === true ? "是" : "否"}/><DetailRow label="关系" value={factText || "—"}/><DetailRow label="路径" value={pathText || "—"}/><DetailRow label="错误" value={typeof data?.graph_memory_error === "string" ? localizeDisplayText(data.graph_memory_error) : "—"}/></section>;
}

export function ApiDispatchDetailPage({ taskId }: { taskId: string }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const [overrideHistory, setOverrideHistory] = useState<RuntimeOverrideHistory | null>(null);
  const [publicationReceipt, setPublicationReceipt] = useState<DispatchPublicationResponse | null>(null);
  const [publicationError, setPublicationError] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const canPublish = useHasPermission(PERMISSIONS.DISPATCH_REVIEW);
  const refresh = useCallback(() => setRefreshKey((value) => value + 1), []);
  const { status, result, error, loading } = useTaskApi(taskId, refreshKey);
  const { agents, connection, events } = useTaskEvents(taskId, refresh);
  const eventData = (type: string) => events.filter((event) => event.event_type === type).at(-1)?.data;
  const graphMemoryData = events.filter((event) => event.node === "graph_memory").at(-1)?.data;
  const publication = publicationReceipt ?? result?.publication ?? null;
  const publishRoute = useCallback(async () => {
    if (!window.confirm("确认发布这条调度路线？发布后对应员工将看到行驶路线和说明。")) return;
    setPublishing(true);
    setPublicationError(null);
    try {
      setPublicationReceipt(await publishDispatchTask(taskId));
    } catch (error: unknown) {
      if (error instanceof ApiError && error.message) setPublicationError(error.message);
      else setPublicationError("调度路线发布失败，请稍后重试。");
    } finally {
      setPublishing(false);
    }
  }, [taskId]);
  const state = taskStateCopy(error?.code ?? status?.status ?? "PROCESSING");
  if (loading) return <div className="loading-state">正在读取真实调度任务…</div>;
  if (error) return <div className="dispatch-page"><div className="error-banner" role="alert"><strong>{state.title}</strong><span>{state.description}</span><Link className="button-primary" to="/dispatch">发起新的智能调度</Link></div></div>;
  if (!status) return null;

  const latestOverride = overrideHistory?.items[0];
  const evidenceScenario = resolveEvidenceScenario(result?.anomaly_type, result?.vehicle_allocation, result?.route_plan);
  return <div className="dispatch-page"><div className="dispatch-command"><div><p className="eyebrow">任务 / {status.task_id}</p><h2>{state.title}</h2></div><StatusPill status={status.status}/></div>
    <div className="detail-tabs"><button className="selected">真实任务状态</button></div>
    <DispatchEvidenceOverview anomalyType={result?.anomaly_type} vehicleAllocation={result?.vehicle_allocation} routePlan={result?.route_plan}/>
    {!canPublish && publication?.status === "PUBLISHED" && result?.route_plan?.real_road_route ? <PublishedAmapRouteMap routePlan={result.route_plan} publication={publication}/> : null}
    {canPublish && result?.anomaly_type === "VEHICLE_BREAKDOWN" ? <VehicleOperationDispatchPanel taskId={taskId}/> : canPublish ? <LiveVehicleMap anomalyType={result?.anomaly_type} allocation={result?.vehicle_allocation} routePlan={result?.route_plan} connection={connection} events={events}/> : null}
    <div className="dispatch-layout"><aside className="context-column"><section className="context-panel"><div className="panel-heading"><div><p className="eyebrow">任务上下文</p><h2>调度任务</h2></div><CircleAlert size={18}/></div><DetailRow label="任务 ID" value={status.task_id}/><DetailRow label="运单" value={String(status.order_id)}/><DetailRow label="状态" value={localizeStatus(status.status)}/><DetailRow label="开始时间" value={status.started_at ?? "暂无数据"}/><DetailRow label="完成时间" value={status.completed_at ?? "暂无数据"}/></section></aside>
      <main className="decision-column"><section className="decision-reason"><div className="panel-heading"><div><p className="eyebrow">异步智能调度</p><h2>{state.title}</h2></div></div><p>{state.description}</p><p className="api-disclaimer">实时节点状态将在 WebSocket 连接后显示。</p></section>{evidenceScenario.vehicle && result?.vehicle_allocation ? <FleetAllocationPanel allocation={result.vehicle_allocation}/> : null}{evidenceScenario.route && result?.route_plan ? <RoutePlanResultPanel routePlan={result.route_plan} pickupEdgeIds={result.vehicle_allocation?.pickup_route?.edge_ids ?? []}/> : null}{result?.ready && <section className="route-decision"><div className="panel-heading"><div><p className="eyebrow">调度结果</p><h2>真实调度结果</h2></div><RouteIcon size={18}/></div>{result.dispatch ? <div className="detail-list"><DetailRow label="原始路线" value={result.dispatch.original_route_id ?? "暂无数据"}/><DetailRow label="推荐路线" value={result.dispatch.target_route_id ?? "待主管发布"}/><DetailRow label="决策理由" value={localizeDisplayText(result.dispatch.decision_reason ?? "待主管发布")}/><DetailRow label="降级状态" value={result.dispatch.fallback_used ? localizeDisplayText(result.dispatch.fallback_reason ?? "已启用") : "未启用"}/><DetailRow label="版本" value={String(result.dispatch.version)}/></div> : <p className="api-disclaimer">暂无调度结果。</p>}</section>}
        {result?.ready && result.dispatch ? <section className="audit-panel publication-panel"><div className="panel-heading"><div><p className="eyebrow">本地演示发布</p><h2>{publication?.status === "PUBLISHED" ? "调度路线已发布" : "调度路线待发布"}</h2></div><StatusPill status={publication?.status ?? "PENDING"}/></div><p className="api-disclaimer">只记录到本地演示系统，不连接企业、车辆或司机外部平台。</p><div className="detail-list"><DetailRow label="接收员工" value={publication?.recipient_display_name ?? "未指定"}/><DetailRow label="员工编号" value={publication?.recipient_employee_id ?? "—"}/>{publication?.status === "PUBLISHED" ? <><DetailRow label="已发布路线" value={publication.route_id ?? "—"}/><DetailRow label="行驶说明" value={publication.route_instruction ?? "—"}/><DetailRow label="发布时间" value={publication.published_at ?? "—"}/><DetailRow label="发布人" value={publication.published_by ?? "—"}/></> : null}</div>{publicationError ? <p className="review-decision-feedback error" role="alert">{publicationError}</p> : null}{canPublish && result.audit?.result === "APPROVED" && publication?.status !== "PUBLISHED" ? <button type="button" className="button-primary" disabled={publishing} onClick={publishRoute}>{publishing ? "正在发布…" : "发布调度单"}</button> : null}</section> : null}
        <RoutingEvidencePanel events={events}/><AuditEvidencePanel events={events}/>{result?.ready && <section className="audit-panel"><div className="panel-heading"><div><p className="eyebrow">最终审核</p><h2>审核结果</h2></div><ShieldCheck size={18}/></div>{latestOverride ? <div className="detail-list"><DetailRow label="运行态干预" value={`${localizeStatus(latestOverride.status)} · ${latestOverride.operator_id}`}/><DetailRow label="实体 / 字段" value={`${localizeEntityType(latestOverride.entity_type)} ${latestOverride.entity_id} · ${localizeField(latestOverride.field)}`}/><DetailRow label="运行态变更" value={`${localizeStatus(latestOverride.old_value)} → ${localizeStatus(latestOverride.new_value)}`}/><DetailRow label="原因" value={latestOverride.reason}/><DetailRow label="版本" value={`V${latestOverride.before_state_version ?? "—"} → V${latestOverride.after_state_version ?? "—"}`}/><DetailRow label="检查点" value={`${latestOverride.source_checkpoint_id ?? "—"} → ${latestOverride.result_checkpoint_id ?? "—"}`}/></div> : null}{result.audit ? <div className="detail-list"><DetailRow label="结果" value={localizeStatus(result.audit.result)}/><DetailRow label="原因" value={localizeDisplayText(result.audit.reason)}/></div> : <p className="api-disclaimer">暂无审核结果。</p>}</section>}</main>
      <aside className="pipeline-column">{canPublish ? <RuntimeWorkbench taskId={taskId} enabled={runtimeConfig.runtimeThreadStateEnabled} mode="api" events={events} onRuntimeRefresh={refresh} onHistoryChange={setOverrideHistory}/> : null}<AgentPipeline agents={agents}/><section className="pipeline-panel"><p className="eyebrow">任务事件</p><h2>{localizeStatus(connection)}</h2><p className="api-disclaimer">{events.length ? `已接收 ${events.length} 个真实事件。` : "等待任务快照。"}</p></section><EventData label="记忆事件" data={eventData("MEMORY_COMPLETED")} fields={["memory_id", "score", "recommendation", "resolution", "evidence", "matched"]}/><GraphMemoryEventData data={graphMemoryData}/><EventData label="环境降级事件" data={eventData("ENVIRONMENT_FALLBACK")} fields={["fallback_reason", "environment_elapsed_ms", "environment_risk"]}/><EventData label="路径事件" data={eventData("ROUTING_COMPLETED")} fields={["recommended_route", "decision", "memory_adopted", "adopted_memory_id"]}/><EventData label="调度事件" data={eventData("DISPATCH_COMPLETED")} fields={["status", "executed", "version", "route", "manual_review"]}/><EventData label="审核事件" data={eventData("AUDIT_COMPLETED")} fields={["result", "reason", "checks"]}/></aside>
    </div></div>;
}
