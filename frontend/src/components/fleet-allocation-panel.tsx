import { ArrowRight, Truck, UserRound } from "lucide-react";

import type { FleetScoreComponentsResponse, VehicleAllocationResponse, VehicleCandidateResponse } from "../services/api/dispatch-adapter";
import { localizeStatus } from "../utils/presentation-labels";

const EMPTY_EVIDENCE = "未提供";

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

const SCORE_KEYS = Object.keys(SCORE_LABELS) as (keyof FleetScoreComponentsResponse)[];

function evidence(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? EMPTY_EVIDENCE : String(value);
}

function evidenceWithUnit(value: string | number | null | undefined, unit: string): string {
  const displayValue = evidence(value);
  return displayValue === EMPTY_EVIDENCE ? displayValue : `${displayValue} ${unit}`;
}

function localizedEvidenceStatus(value: string | null): string {
  return value ? localizeStatus(value) : EMPTY_EVIDENCE;
}

function candidateDecision(candidate: VehicleCandidateResponse, selectedId: string | null): string[] {
  if (candidate.exclusion_reasons.length) {
    return candidate.exclusion_reasons.map((reason) => EXCLUSION_LABELS[reason] ?? reason);
  }
  if (candidate.vehicle_id === selectedId) return ["接口结果标记为入选车辆"];
  if (candidate.eligible === true) return ["满足硬约束"];
  if (candidate.eligible === false) return ["未提供排除原因"];
  return ["资格结论未提供"];
}

function eligibilityLabel(candidate: VehicleCandidateResponse, selectedId: string | null): string {
  if (candidate.vehicle_id === selectedId) return "已入选";
  if (candidate.eligible === true) return "满足硬约束";
  if (candidate.eligible === false) return "已排除";
  return "资格未提供";
}

function ScoreComponents({ components, className = "fleet-score-components" }: { components: FleetScoreComponentsResponse | null; className?: string }) {
  if (!components) return <span className="fleet-evidence-empty">{EMPTY_EVIDENCE}</span>;
  return <dl className={className}>{SCORE_KEYS.map((key) => <div key={key}><dt>{SCORE_LABELS[key]}</dt><dd>{evidence(components[key])}</dd></div>)}</dl>;
}

export function FleetAllocationPanel({ allocation }: { allocation: VehicleAllocationResponse }) {
  const selected = allocation.candidate_vehicles.find((candidate) => candidate.vehicle_id === allocation.target_vehicle_id) ?? null;
  const pickup = allocation.pickup_route ?? selected?.pickup_route ?? null;
  const pickupDistance = pickup?.distance_km ?? selected?.pickup_distance_km ?? null;
  const pickupMinutes = pickup?.estimated_minutes ?? selected?.pickup_eta_minutes ?? null;

  return <section className="fleet-allocation-panel" aria-labelledby="fleet-allocation-title">
    <div className="panel-heading"><div><p className="eyebrow">车辆故障智能接替</p><h2 id="fleet-allocation-title">替代车辆调度计算</h2></div><Truck size={18}/></div>
    <div className="fleet-transfer" aria-label="故障车辆到接替车辆">
      <article className="fleet-transfer-card is-original"><span>故障车辆</span><strong>{evidence(allocation.original_vehicle_id)}</strong></article>
      <div className="fleet-transfer-arrow"><ArrowRight aria-hidden="true"/><span>{pickupDistance !== null && pickupMinutes !== null ? `接驳 ${pickupDistance} 公里 · ${pickupMinutes} 分钟` : "等待接驳路线"}</span></div>
      <article className="fleet-transfer-card is-selected"><span>接替车辆</span><strong>{evidence(allocation.target_vehicle_id)}</strong><span className="fleet-driver"><UserRound size={13}/>司机 {allocation.target_driver_id ?? "未分配"}</span></article>
    </div>
    <div className="fleet-score-summary"><span>入选评分</span><strong>{evidence(selected?.score)}</strong><small>评分公式：{evidence(allocation.scoring_formula)}</small></div>
    <ScoreComponents components={selected?.score_components ?? null}/>
    <div className="fleet-candidate-heading"><h3>全部候选车辆</h3><span>{allocation.candidate_vehicles.length} 辆</span></div>
    <div className="fleet-candidate-table-wrap">
      <table className="fleet-candidate-table">
        <caption>车辆候选证据表：逐车核对资格、接驳与评分依据</caption>
        <thead><tr>
          <th scope="col">车辆</th><th scope="col">资格与原因</th><th scope="col">司机</th><th scope="col">车辆状态</th><th scope="col">剩余载重</th><th scope="col">车辆证据</th><th scope="col">接驳距离</th><th scope="col">接驳时间</th><th scope="col">评分</th><th scope="col">评分分项</th>
        </tr></thead>
        <tbody>{allocation.candidate_vehicles.map((candidate) => {
          const isSelected = candidate.vehicle_id === allocation.target_vehicle_id;
          return <tr
            key={candidate.vehicle_id}
            className={`fleet-candidate ${isSelected ? "is-selected" : candidate.eligible ? "is-eligible" : "is-excluded"}`}
            data-vehicle-id={candidate.vehicle_id}
            aria-label={`${candidate.vehicle_id} 候选车辆`}
          >
            <th scope="row">{candidate.vehicle_id}</th>
            <td data-field="eligibility"><strong>{eligibilityLabel(candidate, allocation.target_vehicle_id)}</strong><ul>{candidateDecision(candidate, allocation.target_vehicle_id).map((reason) => <li key={reason}>{reason}</li>)}</ul></td>
            <td data-field="driver"><strong>{candidate.driver_id ?? "未分配"}</strong><small>{localizedEvidenceStatus(candidate.driver_status)}</small></td>
            <td data-field="vehicle-status">{localizedEvidenceStatus(candidate.vehicle_status)}</td>
            <td data-field="remaining-capacity">{evidenceWithUnit(candidate.remaining_capacity_kg, "千克")}</td>
            <td data-field="vehicle-evidence"><span>总重 {evidenceWithUnit(candidate.gross_weight_tons, "吨")}</span><span>能力 {evidence(candidate.cargo_capability)}</span></td>
            <td data-field="pickup-distance">{evidenceWithUnit(candidate.pickup_distance_km, "公里")}</td>
            <td data-field="pickup-eta">{evidenceWithUnit(candidate.pickup_eta_minutes, "分钟")}</td>
            <td data-field="score">{evidence(candidate.score)}</td>
            <td data-field="score-components"><ScoreComponents components={candidate.score_components} className="fleet-candidate-score-components"/></td>
          </tr>;
        })}</tbody>
      </table>
    </div>
  </section>;
}