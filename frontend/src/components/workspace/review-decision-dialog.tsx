import { useEffect, useRef } from "react";

import type { ReviewDecision } from "../../services/api/review-decision-client";
import type { ReviewListItem } from "../../types/workspace-read-models";

export function ReviewDecisionDialog({ item, decision, reason, pending, error, onReasonChange, onCancel, onConfirm, returnFocus }: {
  item: ReviewListItem;
  decision: ReviewDecision;
  reason: string;
  pending: boolean;
  error: string | null;
  onReasonChange: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
  returnFocus?: HTMLElement | null;
}) {
  const dialogRef = useRef<HTMLElement>(null);
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previousFocus.current = returnFocus ?? document.activeElement as HTMLElement | null;
    reasonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !pending) {
        event.preventDefault();
        onCancel();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), textarea, [tabindex]:not([tabindex="-1"])')];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previousFocus.current?.focus();
    };
  }, [onCancel, pending, returnFocus]);

  const rejecting = decision === "REJECT";
  const confirmDisabled = pending || (rejecting && reason.trim().length < 2);
  const title = rejecting ? "确认拒绝该调度方案" : "确认批准该调度方案";
  return <div className="runtime-dialog-backdrop review-dialog-backdrop">
    <section ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="review-dialog-title" className="review-decision-dialog" data-surface="dialog">
      <p className="eyebrow">人工复核决定</p>
      <h2 id="review-dialog-title">{title}</h2>
      <div className="detail-list">
        <div><span>任务</span><strong>{item.task_id}</strong></div>
        <div><span>运单</span><strong>{item.order_no ?? "—"}</strong></div>
        <div><span>路线</span><strong>{item.original_route_id ?? "—"} → {item.suggested_route_id ?? "—"}</strong></div>
        <div><span>风险原因</span><strong>{item.reason ?? "—"}</strong></div>
      </div>
      <label className="review-decision-form">
        {rejecting ? "拒绝原因（必填）" : "批准备注（选填）"}
        <textarea
          ref={reasonRef}
          aria-label="复核说明"
          maxLength={500}
          placeholder={rejecting ? "请填写至少 2 个字符的拒绝原因" : "可填写批准依据"}
          value={reason}
          onChange={(event) => onReasonChange(event.target.value)}
        />
      </label>
      <p className="review-decision-warning">决定将写入本地 MySQL 并生成审计记录；提交后不能在本页面撤销。</p>
      {error ? <p className="review-decision-feedback error" role="alert">{error}</p> : null}
      <div className="command-actions">
        <button type="button" className="button-secondary" disabled={pending} onClick={onCancel}>取消</button>
        <button type="button" className={rejecting ? "button-danger" : "button-primary"} disabled={confirmDisabled} onClick={onConfirm}>
          {pending ? "正在提交…" : rejecting ? "确认拒绝" : "确认批准"}
        </button>
      </div>
    </section>
  </div>;
}

