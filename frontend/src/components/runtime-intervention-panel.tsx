import { useState } from "react";

import type { ReturnTypeUseRuntimeOverride } from "../types/runtime-workbench";
import { localizeNode, localizeStatus } from "../utils/presentation-labels";
import { RuntimeOverrideDialog } from "./runtime-override-dialog";

const eligibilityCopy: Record<string, string> = {
  NOT_STABLE: "当前智能体正在执行，暂不可干预",
  TERMINAL: "任务已经结束，不能修改运行状态",
  NO_PERMISSION: "无权限执行运行态强干预",
  WRONG_BOUNDARY: "当前不在环境 → 运力安全边界",
  BUSY: "当前运行线程正在被其他操作修改",
};

export function RuntimeInterventionPanel({ override, canOverride = true }: { override: ReturnTypeUseRuntimeOverride; canOverride?: boolean }) {
  const [returnFocus, setReturnFocus] = useState<HTMLButtonElement | null>(null);
  if (override.loading) return <section className="runtime-intervention-panel"><p>正在读取干预资格…</p></section>;
  if (override.unavailable || !override.context) return <section className="runtime-intervention-panel"><h2>运行态干预</h2><p>运行时干预暂时不可用</p></section>;
  const context = override.context;
  const allowed = new Set(["BROKEN", "UNAVAILABLE", "MAINTENANCE"]);
  const values = ["BROKEN", "UNAVAILABLE", "MAINTENANCE"] as const;
  const enabled = canOverride && context.eligibility === "ELIGIBLE" && context.can_override;
  return <section className="runtime-intervention-panel" aria-label="运行态干预" data-testid="runtime-intervention">
    <div className="panel-heading"><div><p className="eyebrow">安全边界控制</p><h2>运行态干预</h2></div><span>{localizeStatus(context.eligibility)}</span></div>
    <div className="detail-list"><div><span>车辆</span><strong>{context.target?.display_name ?? "—"}</strong></div><div><span>状态</span><strong>{localizeStatus(context.target?.current_value)}</strong></div><div><span>安全边界</span><strong>{localizeNode(context.current_node)} → {localizeNode(context.next_node ?? "END")}</strong></div><div><span>版本</span><strong>{context.state_version}</strong></div></div>
    {!enabled ? <p className="runtime-disabled-reason">{!canOverride ? eligibilityCopy.NO_PERMISSION : eligibilityCopy[context.eligibility] ?? context.eligibility_reason_code}</p> : null}
    <div className="runtime-actions">{values.map((value) => <button key={value} data-target={value} disabled={!enabled || !allowed.has(value) || !context.target?.allowed_new_values.includes(value)} onClick={(event) => { setReturnFocus(event.currentTarget); override.open(value); }}>{localizeStatus(value)}</button>)}</div>
    {override.message ? <div aria-live="polite" data-submission-state={override.submission} className={`runtime-result ${override.submission.toLowerCase()}`}><strong>{localizeStatus(override.submission)}</strong><span>{override.message}</span>{override.result?.before_state_version !== null && override.result?.after_state_version !== null ? <span>V{override.result?.before_state_version} → V{override.result?.after_state_version} · {override.result?.result_checkpoint_id}</span> : null}</div> : null}
    {override.snapshot ? <RuntimeOverrideDialog snapshot={override.snapshot} context={context} reason={override.reason} stale={override.stale} submission={override.submission} setReason={override.setReason} onCancel={override.close} onConfirm={override.submit} returnFocus={returnFocus} /> : null}
  </section>;
}
