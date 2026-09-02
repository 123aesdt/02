import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { DataTable, type DataTableColumn } from "../components/ui/data-table";
import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import { ReviewDecisionDialog } from "../components/workspace/review-decision-dialog";
import { RoleWorkspaceFrame } from "../components/workspace/role-workspace-frame";
import { WorkspaceSection } from "../components/workspace/workspace-section";
import { runtimeConfig } from "../config/runtime";
import { useReviewsRead } from "../hooks/use-workspace-reads";
import { ApiError } from "../services/api/client";
import { reviewDecisionClient, type ReviewDecision } from "../services/api/review-decision-client";
import type { ReviewListItem, WorkspaceReadProvenance } from "../types/workspace-read-models";
import { localizeStatus } from "../utils/presentation-labels";

function provenanceLabel(provenance: WorkspaceReadProvenance) {
  return provenance === "LIVE" ? "实时数据" : provenance === "MIXED" ? "混合数据" : "演示数据";
}

interface ReviewTableRow extends ReviewListItem { actions?: never }

const reviewColumns: DataTableColumn<ReviewTableRow>[] = [
  { key: "task_id", label: "任务", render: (item) => <Link to={`/dispatch/${item.task_id}`}>{item.task_id}</Link> },
  { key: "order_no", label: "运单" },
  { key: "risk", label: "风险", render: (item) => localizeStatus(item.risk) },
  { key: "ai_analysis_reason", label: "AI 分析原因", render: (item) => item.ai_analysis_reason ?? item.reason ?? "等待重新分析" },
  { key: "ai_recommended_action", label: "AI 处置建议", render: (item) => item.ai_recommended_action ?? "等待重新分析" },
  { key: "vehicle_id", label: "车辆" },
  { key: "original_route_id", label: "原路线" },
  { key: "suggested_route_id", label: "建议路线", render: (item) => item.suggested_route_id ?? "当前不适用" },
  { key: "ai_analysis_mode", label: "AI 状态", render: (item) => item.ai_analysis_mode ? <StatusBadge status="COMPLETED" label="8-Agent 分析完成" /> : <StatusBadge status="PENDING" label="等待重新分析" /> },
  { key: "status", label: "状态", render: (item) => <StatusBadge status={item.status} label={item.status === "REVIEW_REQUIRED" ? "等待人工复核" : localizeStatus(item.status)} /> },
  { key: "created_at", label: "进入复核时间" },
];

function decisionError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "REVIEW_ALREADY_DECIDED") return "该任务已由其他人员处理，请刷新列表。";
    if (error.code === "DISPATCH_VERSION_CONFLICT") return "调度方案已发生变化，请刷新后重新确认。";
    if (error.status === 403) return "当前账号没有人工复核权限。";
    if (error.status === 404) return "该复核任务已不存在，请刷新列表。";
    if (error.status === 422) return "复核说明不符合要求，请检查后重试。";
    if (error.message) return error.message;
  }
  return "复核决定提交失败，请稍后重试。";
}

function ReviewReadFeedback({ state, onRetry, paged }: { state: string; onRetry: () => void; paged: boolean }) {
  if (state === "LOADING") return <Skeleton label="正在加载人工复核队列" lines={5} />;
  if (state === "EMPTY") return <EmptyState kind="empty" title={paged ? "当前分页没有等待人工复核任务" : "当前没有等待人工复核任务"} description="接口已连接，当前筛选范围为空。" action={<button type="button" onClick={onRetry}>重新读取</button>} />;
  if (state === "FORBIDDEN") return <EmptyState kind="forbidden" title="没有查看人工复核队列的权限" description="需要 dispatch:review 权限。" action={<button type="button" onClick={onRetry}>重试</button>} />;
  if (state === "UNAVAILABLE") return <EmptyState kind="unavailable" title="人工复核队列服务暂不可用" description="请稍后重试；不会回退演示数据。" action={<button type="button" onClick={onRetry}>重试</button>} />;
  if (state === "NOT_EXPOSED") return <EmptyState kind="not-exposed" title="人工复核队列未开放" description="当前模式没有批准的复核读取来源。" />;
  return <EmptyState kind="error" title="人工复核队列加载失败" description="未显示任何推测任务，请重试。" action={<button type="button" onClick={onRetry}>重试</button>} />;
}

function ApiReviewsPage() {
  const [cursor, setCursor] = useState<string | null>(null);
  const [history, setHistory] = useState<(string | null)[]>([]);
  const read = useReviewsRead({ limit: 20, cursor });
  const [selected, setSelected] = useState<{ item: ReviewListItem; decision: ReviewDecision; trigger: HTMLElement | null } | null>(null);
  const [reason, setReason] = useState("");
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);
  const [decisionFeedback, setDecisionFeedback] = useState<string | null>(null);
  const [successFeedback, setSuccessFeedback] = useState<string | null>(null);
  const reset = () => { setCursor(null); setHistory([]); };
  const previous = () => {
    const previousCursor = history.at(-1) ?? null;
    setHistory((items) => items.slice(0, -1));
    setCursor(previousCursor);
  };
  const pagination = history.length ? <div><button type="button" onClick={previous}>上一页</button><button type="button" onClick={reset}>返回首页</button></div> : null;
  const openDecision = useCallback((item: ReviewListItem, decision: ReviewDecision, trigger: HTMLElement) => {
    setSelected({ item, decision, trigger });
    setReason("");
    setDecisionFeedback(null);
    setSuccessFeedback(null);
  }, []);
  const closeDecision = useCallback(() => {
    if (pendingTaskId === null) setSelected(null);
  }, [pendingTaskId]);
  const submitDecision = useCallback(async () => {
    if (selected === null) return;
    setPendingTaskId(selected.item.task_id);
    setDecisionFeedback(null);
    try {
      const normalizedReason = reason.trim();
      await reviewDecisionClient.decide(selected.item.task_id, {
        decision: selected.decision,
        ...(normalizedReason ? { reason: normalizedReason } : {}),
      });
      setSuccessFeedback(selected.decision === "APPROVE" ? "任务已批准，待复核列表已刷新。" : "任务已拒绝，待复核列表已刷新。");
      setSelected(null);
      read.refresh();
    } catch (error: unknown) {
      setDecisionFeedback(decisionError(error));
    } finally {
      setPendingTaskId(null);
    }
  }, [read, reason, selected]);
  const columns = useMemo<DataTableColumn<ReviewTableRow>[]>(() => [
    ...reviewColumns,
    {
      key: "actions",
      label: "操作",
      render: (item) => <div className="review-row-actions">
        <button type="button" className="button-primary review-action" disabled={pendingTaskId === item.task_id} onClick={(event) => openDecision(item, "APPROVE", event.currentTarget)}>批准</button>
        <button type="button" className="button-secondary review-action reject" disabled={pendingTaskId === item.task_id} onClick={(event) => openDecision(item, "REJECT", event.currentTarget)}>拒绝</button>
      </div>,
    },
  ], [openDecision, pendingTaskId]);

  return <RoleWorkspaceFrame title="待复核" description="对高风险调度方案执行人工批准或拒绝，决定将写入本地演示数据库。">
    {successFeedback ? <p className="review-decision-feedback success" role="status">{successFeedback}</p> : null}
    <WorkspaceSection id="reviews-list" title="人工复核队列" description="可查看任务详情，并对仍处于待复核状态的方案作出决定。">
      {read.state === "READY" ? <>
        <div className="panel-heading"><span className={`source-label ${read.data.provenance === "LIVE" ? "live" : "demo"}`}>{provenanceLabel(read.data.provenance)}</span></div>
        <DataTable caption="待人工复核队列" columns={columns} rows={read.data.items} rowKey={(item) => String(item.row_id)} />
        {read.data.next_cursor ? <button type="button" onClick={() => { setHistory((items) => [...items, cursor]); setCursor(read.data.next_cursor); }}>下一页</button> : null}
        {pagination}
      </> : <>
        <ReviewReadFeedback state={read.state} onRetry={read.refresh} paged={history.length > 0} />
        {pagination}
      </>}
    </WorkspaceSection>
    {selected ? <ReviewDecisionDialog
      item={selected.item}
      decision={selected.decision}
      reason={reason}
      pending={pendingTaskId === selected.item.task_id}
      error={decisionFeedback}
      onReasonChange={setReason}
      onCancel={closeDecision}
      onConfirm={submitDecision}
      returnFocus={selected.trigger}
    /> : null}
  </RoleWorkspaceFrame>;
}

function MockReviewsPage() {
  return <RoleWorkspaceFrame title="待复核" description="只读展示服务端批准的人工复核投影，不提供批准或拒绝动作。">
    <WorkspaceSection id="reviews-list" title="人工复核队列">
      <EmptyState kind="not-exposed" title="演示模式未提供人工复核队列" description="不会用静态任务冒充服务端复核投影。" />
    </WorkspaceSection>
  </RoleWorkspaceFrame>;
}

export function ReviewsPage() {
  return runtimeConfig.dataMode === "api" ? <ApiReviewsPage /> : <MockReviewsPage />;
}
