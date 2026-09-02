import type { TaskEvent } from "../types/task-events";
import { localizeDisplayText, localizeStatus } from "../utils/presentation-labels";

export function CapacityEvidencePanel({ events }: { events: TaskEvent[] }) {
  const item = events.filter((event) => event.event_type === "CAPACITY_COMPLETED").at(-1);
  if (!item) return null;
  const data = item.data;
  return <section className="capacity-evidence-panel" data-testid="capacity-evidence"><p className="eyebrow">运力证据</p><h2>车辆 {String(data.vehicle_id ?? "—")}</h2><div className="detail-list"><div><span>运行态状态</span><strong>{localizeStatus(String(data.vehicle_status ?? "—"))}</strong></div><div><span>可用性</span><strong>车辆可用：{data.vehicle_available === true ? "是" : data.vehicle_available === false ? "否" : "—"}</strong></div><div><span>运力状态</span><strong>{localizeStatus(String(data.capacity_status ?? "—"))}</strong></div><div><span>原因</span><strong>{localizeDisplayText(String(data.reason ?? "—"))}</strong></div></div></section>;
}
