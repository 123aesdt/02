import { useEffect, useRef } from "react";

import type { OverrideDialogSnapshot, OverrideSubmissionState, RuntimeInterventionContext } from "../types/runtime-override";
import { localizeNode, localizeStatus } from "../utils/presentation-labels";

export function RuntimeOverrideDialog({ snapshot, context, reason, stale, submission, setReason, onCancel, onConfirm, returnFocus }: {
  snapshot: OverrideDialogSnapshot; context: RuntimeInterventionContext | null; reason: string; stale: boolean;
  submission: OverrideSubmissionState; setReason: (value: string) => void; onCancel: () => void; onConfirm: () => void;
  returnFocus?: HTMLElement | null;
}) {
  const dialogRef = useRef<HTMLElement>(null);
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  useEffect(() => {
    previousFocus.current = returnFocus ?? document.activeElement as HTMLElement | null;
    reasonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onCancel(); return; }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])')];
      if (!focusable.length) return;
      const first = focusable[0]; const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => { document.removeEventListener("keydown", onKeyDown); previousFocus.current?.focus(); };
  }, [onCancel, returnFocus]);
  const disabled = stale || reason.trim().length < 4 || submission === "SUBMITTING" || submission === "PARTIAL";
  return <div className="runtime-dialog-backdrop"><section ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="override-dialog-title" className="runtime-override-dialog" data-surface="dialog">
    <p className="eyebrow">安全运行态修改</p><h2 id="override-dialog-title">确认车辆状态干预</h2>
    <div className="detail-list">
      <div><span>车辆</span><strong>{context?.target?.display_name ?? snapshot.entityId} · {snapshot.entityId}</strong></div>
      <div><span>状态变更</span><strong>{localizeStatus(snapshot.oldValue)} → {localizeStatus(snapshot.newValue)}</strong></div>
      <div><span>运行线程</span><strong data-testid="captured-version">版本 {snapshot.expectedVersion}</strong></div>
      <div><span>规范检查点</span><strong data-testid="captured-checkpoint">{snapshot.checkpointId}</strong></div>
      <div><span>下一节点</span><strong>{localizeNode(snapshot.expectedNextNode)}</strong></div>
    </div>
    {stale ? <div className="runtime-stale" role="alert">运行状态已变化，请重新发起干预。发起时版本 {snapshot.expectedVersion} · 当前版本 {context?.state_version ?? "—"}</div> : null}
    <label className="runtime-reason">干预原因<textarea ref={reasonRef} aria-label="干预原因" value={reason} onChange={(event) => setReason(event.target.value)} /></label>
    <p className="runtime-warning">此操作将修改规范 LangGraph 运行状态，下一运力节点会读取新状态。</p>
    <div className="command-actions"><button className="button-secondary" onClick={onCancel}>取消</button><button className="button-danger" disabled={disabled} onClick={onConfirm}>{submission === "FAILED" ? "重试同一操作" : "确认干预"}</button></div>
  </section></div>;
}
