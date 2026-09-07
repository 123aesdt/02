import { ArrowRight, Truck, UserRound } from "lucide-react";

import type { FleetScoreComponentsResponse, VehicleAllocationResponse, VehicleCandidateResponse } from "../services/api/dispatch-adapter";
import { localizeStatus } from "../utils/presentation-labels";

const PLATE_BY_VEHICLE_ID: Readonly<Record<string, string>> = {
  "V-001": "新物冷链-01",
  "V-002": "新物厢货-02",
  "V-003": "新物厢货-03",
  "V-004": "新物轻卡-04",
  "V-005": "新物冷链-05",
  "V-006": "新物电运-06",
  "V-007": "新物乡配-07",
  "V-008": "新物轻卡-08",
  "V-009": "新物冷链-09",
  "V-010": "新物农运-10",
  "V-011": "新物冷链-11",
  "V-012": "新物电运-12",
};

const EXCLUSION_LABELS: Readonly<Record<string, string>> = {
  ORIGINAL_VEHICLE_EXCLUDED: "原故障车辆不参与候选",
  VEHICLE_UNAVAILABLE: "车辆当前不可用",
  DRIVER_UNAVAILABLE: "司机当前不可用",
  LICENSE_MISMATCH: "驾驶证准驾车型不匹配",
  INSUFFICIENT_CAPACITY: "剩余载重不足",
  CARGO_CAPABILITY_MISMATCH: "冷链能力不匹配",
  ROAD_WEIGHT_RESTRICTION: "道路限重不满足",
  PICKUP_UNREACHABLE: "无法到达接驳点",
  DELIVERY_UNREACHABLE: "无法完成后续配送",
};

const SCORE_LABELS: Readonly<Record<keyof FleetScoreComponentsResponse, string>> = {
  eta_penalty: "接驳时间扣分",
  distance_penalty: "接驳距离扣分",
  load_penalty: "载重占用扣分",
  road_risk_penalty: "道路风险扣分",
  same_station_bonus: "同站加分",
  cargo_exact_match_bonus: "货物能力匹配加分",
};

function plate(vehicleId: string | null): string {
  if (!vehicleId) return "未分配";
  return PLATE_BY_VEHICLE_ID[vehicleId] ?? vehicleId;
}

function candidateDecision(candidate: VehicleCandidateResponse, selectedId: string | null): string[] {
  if (candidate.exclusion_reasons.length) {
    return candidate.exclusion_reasons.map((reason) => EXCLUSION_LABELS[reason] ?? reason);
  }
  if (candidate.vehicle_id === selectedId) return ["满足全部约束，综合评分最高"];
  if (candidate.eligible) return ["满足约束，综合评分低于入选车辆"];
  return ["未进入可调度车辆集合"];
}

function ScoreComponents({ components }: { components: FleetScoreComponentsResponse | null }) {
  if (!components) return null;
  const entries = (Object.keys(SCORE_LABELS) as (keyof FleetScoreComponentsResponse)[])
    .filter((key) => components[key] !== null);
  if (!entries.length) return null;
  return <dl className="fleet-score-components">{entries.map((key) => <div key={key}><dt>{SCORE_LABELS[key]}</dt><dd>{components[key]}</dd></div>)}</dl>;
}

export function FleetAllocationPanel({ allocation }: { allocation: VehicleAllocationResponse }) {
  const selected = allocation.candidate_vehicles.find((candidate) => candidate.vehicle_id === allocation.target_vehicle_id) ?? null;
  const pickup = allocation.pickup_route ?? selected?.pickup_route ?? null;
  const pickupDistance = pickup?.distance_km ?? selected?.pickup_distance_km ?? null;
  const pickupMinutes = pickup?.estimated_minutes ?? selected?.pickup_eta_minutes ?? null;

  return <section className="fleet-allocation-panel" aria-labelledby="fleet-allocation-title">
    <div className="panel-heading"><div><p className="eyebrow">车辆故障智能接替</p><h2 id="fleet-allocation-title">替代车辆调度计算</h2></div><Truck size={18}/></div>
    <div className="fleet-transfer" aria-label="故障车辆到接替车辆">
      <article className="fleet-transfer-card is-original"><span>故障车辆</span><strong>{plate(allocation.original_vehicle_id)}</strong><small>{allocation.original_vehicle_id ?? "—"}</small></article>
      <div className="fleet-transfer-arrow"><ArrowRight aria-hidden="true"/><span>{pickupDistance !== null && pickupMinutes !== null ? `接驳 ${pickupDistance} 公里 · ${pickupMinutes} 分钟` : "等待接驳路线"}</span></div>
      <article className="fleet-transfer-card is-selected"><span>接替车辆</span><strong>{plate(allocation.target_vehicle_id)}</strong><small>{allocation.target_vehicle_id ?? "—"}</small><span className="fleet-driver"><UserRound size={13}/>司机 {allocation.target_driver_id ?? "未分配"}</span></article>
    </div>
    <div className="fleet-score-summary"><span>入选评分</span><strong>{selected?.score ?? "—"}</strong><small>评分公式：{allocation.scoring_formula}</small></div>
    <ScoreComponents components={selected?.score_components ?? null}/>
    <div className="fleet-candidate-heading"><h3>全部候选车辆</h3><span>{allocation.candidate_vehicles.length} 辆</span></div>
    <div className="fleet-candidates">{allocation.candidate_vehicles.map((candidate) => {
      const isSelected = candidate.vehicle_id === allocation.target_vehicle_id;
      const vehiclePlate = plate(candidate.vehicle_id);
      return <article
        key={candidate.vehicle_id}
        className={`fleet-candidate ${isSelected ? "is-selected" : candidate.eligible ? "is-eligible" : "is-excluded"}`}
        data-vehicle-id={candidate.vehicle_id}
        aria-label={`${vehiclePlate}（${candidate.vehicle_id}）候选车辆`}
      >
        <header><h3>{vehiclePlate}<small>{candidate.vehicle_id}</small></h3><span>{isSelected ? "已入选" : candidate.eligible ? "可调度" : "已排除"}</span></header>
        <dl><div><dt>司机</dt><dd>{candidate.driver_id ?? "未分配"}</dd></div><div><dt>车辆</dt><dd>{localizeStatus(candidate.vehicle_status)}</dd></div><div><dt>剩余载重</dt><dd>{candidate.remaining_capacity_kg ? `${candidate.remaining_capacity_kg} 千克` : "—"}</dd></div><div><dt>评分</dt><dd>{candidate.score ?? "—"}</dd></div></dl>
        <ul>{candidateDecision(candidate, allocation.target_vehicle_id).map((reason) => <li key={reason}>{reason}</li>)}</ul>
      </article>;
    })}</div>
  </section>;
}
