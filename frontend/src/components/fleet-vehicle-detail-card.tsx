import { AlertTriangle, ArrowRight, Gauge, MapPin, Route, Timer, Truck, UserRound, Weight, X } from "lucide-react";

import type { FleetRoute } from "../features/fleet-sandbox/fleet-sandbox-data";
import type { FleetPositionSnapshot } from "../features/fleet-sandbox/fleet-simulation";
import type { DispatchImpactResponse } from "../services/api/dispatch-adapter";

interface FleetVehicleDetailCardProps {
  vehicle: FleetPositionSnapshot;
  route: FleetRoute;
  trip: {
    nextStop: string;
    remainingKm: number;
    etaMinutes: number;
  };
  statusLabel: string;
  statusColor: string;
  driverId?: string | null;
  statusReason?: string | null;
  impact?: DispatchImpactResponse | null;
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

export function FleetVehicleDetailCard({
  vehicle,
  route,
  trip,
  statusLabel,
  statusColor,
  driverId,
  statusReason,
  impact = null,
  onClose,
}: FleetVehicleDetailCardProps) {
  return <aside
    className={`fleet-dispatch-impact fleet-vehicle-detail${impact ? ` is-${impact.calculation_status.toLowerCase()}` : ""}`}
    data-fleet-vehicle-detail={vehicle.id}
    data-dispatch-impact={impact?.calculation_status}
    aria-label={`${vehicle.id}车辆运行详情`}
  >
    <header>
      <span><Truck size={15}/>车辆运行详情</span>
      <div className="fleet-dispatch-impact__header-actions">
        <b style={{ color: statusColor, borderColor: `${statusColor}66`, background: `${statusColor}1a` }}>{statusLabel}</b>
        <button type="button" aria-label="关闭车辆运行详情" title="关闭" onClick={onClose}><X size={14}/></button>
      </div>
    </header>

    <section className="fleet-vehicle-detail__identity">
      <i style={{ "--vehicle-detail-color": statusColor } as React.CSSProperties}><Truck size={22}/></i>
      <span><strong>{vehicle.id}</strong><small>{route.displayId} · {route.name}</small></span>
    </section>
    <dl className="fleet-vehicle-detail__facts">
      <div className="is-wide"><dt><MapPin size={12}/>当前位置</dt><dd>{vehicle.locationLabel}</dd></div>
      <div><dt><Gauge size={12}/>实时速度</dt><dd>{vehicle.speedKph} km/h</dd></div>
      <div><dt><Route size={12}/>剩余距离</dt><dd>{trip.remainingKm} km</dd></div>
      <div><dt><Timer size={12}/>预计到达</dt><dd>{trip.etaMinutes ? `${trip.etaMinutes} 分钟` : "等待调度"}</dd></div>
      <div><dt><Weight size={12}/>当前载重</dt><dd>{vehicle.loadKg} / {vehicle.capacityKg} kg</dd></div>
      <div><dt><UserRound size={12}/>当前司机</dt><dd>{driverId ?? "未绑定"}</dd></div>
      <div><dt>路线进度</dt><dd>{vehicle.progress}% · 下一站 {trip.nextStop}</dd></div>
      {statusReason ? <div className="is-wide"><dt>状态说明</dt><dd>{statusReason}</dd></div> : null}
    </dl>

    {impact ? <section className="fleet-vehicle-detail__dispatch" aria-label="调度关联与影响">
      <h4><Route size={13}/>调度关联与影响 <b>{impact.calculation_status === "CALCULATED" ? "后端已计算" : "部分数据"}</b></h4>
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
    </section> : null}
  </aside>;
}
