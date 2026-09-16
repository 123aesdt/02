import { AlertTriangle, ArrowRight, Route, Timer, Truck, X } from "lucide-react";

import type { DispatchImpactResponse } from "../services/api/dispatch-adapter";

interface FleetDispatchImpactCardProps {
  impact: DispatchImpactResponse;
  onClose: () => void;
}

function signedDistance(value: string | null): string {
  if (value === null) return "暂无计算依据";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "暂无计算依据";
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(2)} km`;
}

function signedMinutes(value: number | null): string {
  if (value === null) return "暂无计算依据";
  return `${value > 0 ? "+" : ""}${value} 分钟`;
}

function arrivalImpact(minutes: number | null): string {
  if (minutes === null) return "综合数据待补齐";
  if (minutes > 0) return `预计晚到 ${minutes} 分钟`;
  if (minutes < 0) return `预计提前 ${Math.abs(minutes)} 分钟`;
  return "预计到达时间不变";
}

export function FleetDispatchImpactCard({ impact, onClose }: FleetDispatchImpactCardProps) {
  return <aside
    className={`fleet-dispatch-impact is-${impact.calculation_status.toLowerCase()}`}
    data-dispatch-impact={impact.calculation_status}
    aria-label="调度影响分析"
  >
    <header>
      <span><Route size={15}/>调度影响分析</span>
      <div className="fleet-dispatch-impact__header-actions">
        <b>{impact.calculation_status === "CALCULATED" ? "后端已计算" : "部分数据"}</b>
        <button type="button" aria-label="关闭调度影响分析" title="关闭" onClick={onClose}><X size={14}/></button>
      </div>
    </header>
    <div className="fleet-dispatch-impact__relation">
      <article className="is-incident" data-impact-role="incident">
        <i><AlertTriangle size={15}/></i>
        <span><small>故障车辆</small><strong>{impact.incident_vehicle_id}</strong></span>
      </article>
      <ArrowRight className="fleet-dispatch-impact__arrow" size={20}/>
      <article className="is-replacement" data-impact-role="replacement">
        <i><Truck size={15}/></i>
        <span><small>接管车辆</small><strong>{impact.replacement_vehicle_id}</strong></span>
      </article>
    </div>
    <p className="fleet-dispatch-impact__driver">
      <span>接管司机</span><strong>{impact.replacement_driver_id ?? "待分配"}</strong>
    </p>
    <div className="fleet-dispatch-impact__metrics">
      <article data-impact-metric="pickup">
        <small>接管增量</small>
        <strong>{signedDistance(impact.pickup_distance_km)}</strong>
        <span><Timer size={12}/>{signedMinutes(impact.pickup_eta_minutes)}</span>
      </article>
      <article data-impact-metric="route">
        <small>绕行增量</small>
        <strong>{signedDistance(impact.route_distance_delta_km)}</strong>
        <span><Timer size={12}/>{signedMinutes(impact.route_eta_delta_minutes)}</span>
      </article>
      <article className="is-total" data-impact-metric="total">
        <small>综合影响</small>
        <strong>{signedDistance(impact.total_distance_delta_km)}</strong>
        <span>{arrivalImpact(impact.total_delay_minutes)}</span>
      </article>
    </div>
    <footer>综合影响 = 接管增量 + 绕行增量</footer>
  </aside>;
}
