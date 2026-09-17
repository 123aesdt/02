import { ArrowRight, Truck, UserRound } from "lucide-react";

import type { FleetScoreComponentsResponse, VehicleAllocationResponse, VehicleCandidateResponse } from "../services/api/dispatch-adapter";
import { localizeStatus } from "../utils/presentation-labels";

const EMPTY_EVIDENCE = "未记录";

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

function localizedEvidenceStatus(value: string | null, fallback = "状态未记录"): string {
  return value ? localizeStatus(value) : fallback;
}

function pickupEvidence(candidate: VehicleCandidateResponse, value: string | number | null, unit: string): string {
  if (value !== null) return `${value} ${unit}`;
  if (candidate.exclusion_reasons.includes("PICKUP_UNREACHABLE")) return "无法到达";
  return candidate.eligible === false ? "不适用" : "待计算";
}

function scoreEvidence(candidate: VehicleCandidateResponse): string {
  if (candidate.score !== null) return candidate.score;
  return candidate.eligible === false ? "不计分" : "待计算";
}

function rankEvidence(candidate: VehicleCandidateResponse, rank: number | undefined): string {
  if (rank !== undefined) return `第 ${rank} 名`;
  return candidate.eligible === false ? "不参与排名" : "待排名";
}

function candidateDecision(candidate: VehicleCandidateResponse, selectedId: string | null): string[] {
  if (candidate.exclusion_reasons.length) {
    return candidate.exclusion_reasons.map((reason) => EXCLUSION_LABELS[reason] ?? reason);
  }
  if (candidate.vehicle_id === selectedId) return ["接口结果标记为入选车辆"];
  if (candidate.eligible === true) return ["满足硬约束"];
  if (candidate.eligible === false) return ["排除原因待核验"];
  return ["资格结论待核验"];
}

function eligibilityLabel(candidate: VehicleCandidateResponse, selectedId: string | null): string {
  if (candidate.vehicle_id === selectedId) return "已入选";
  if (candidate.eligible === true) return "满足硬约束";
  if (candidate.eligible === false) return "已排除";
  return "资格待核验";
}

function finiteNumber(value: string | number | null | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function rankedCandidates(candidates: VehicleCandidateResponse[]) {
  const eligible = [...candidates.filter((candidate) => candidate.eligible === true)].sort((left, right) => {
    const scoreDifference = finiteNumber(right.score, Number.NEGATIVE_INFINITY) - finiteNumber(left.score, Number.NEGATIVE_INFINITY);
    if (scoreDifference !== 0) return scoreDifference;
    const etaDifference = finiteNumber(left.pickup_eta_minutes, Number.POSITIVE_INFINITY) - finiteNumber(right.pickup_eta_minutes, Number.POSITIVE_INFINITY);
    if (etaDifference !== 0) return etaDifference;
    if (left.vehicle_id < right.vehicle_id) return -1;
    if (left.vehicle_id > right.vehicle_id) return 1;
    return 0;
  });
  const rankByVehicleId = new Map(eligible.map((candidate, index) => [candidate.vehicle_id, index + 1]));
  return { eligible, rankByVehicleId, displayCandidates: [...eligible, ...candidates.filter((candidate) => candidate.eligible !== true)] };
}
function ScoreComponents({ components, className = "fleet-score-components" }: { components: FleetScoreComponentsResponse | null; className?: string }) {
  if (!components) return <span className="fleet-evidence-empty">不计分</span>;
  return <dl className={className}>{SCORE_KEYS.map((key) => <div key={key}><dt>{SCORE_LABELS[key]}</dt><dd>{evidence(components[key])}</dd></div>)}</dl>;
}

export function FleetAllocationPanel({ allocation }: { allocation: VehicleAllocationResponse }) {
  const hasReplacement = allocation.vehicle_reassigned && Boolean(allocation.target_vehicle_id);
  const ranking = rankedCandidates(allocation.candidate_vehicles);
  const selected = allocation.candidate_vehicles.find((candidate) => candidate.vehicle_id === allocation.target_vehicle_id) ?? null;
  const selectedRank = selected ? ranking.rankByVehicleId.get(selected.vehicle_id) ?? null : null;
  const pickup = allocation.pickup_route ?? selected?.pickup_route ?? null;
  const pickupDistance = pickup?.distance_km ?? selected?.pickup_distance_km ?? null;
  const pickupMinutes = pickup?.estimated_minutes ?? selected?.pickup_eta_minutes ?? null;

  return <section className="fleet-allocation-panel" aria-labelledby="fleet-allocation-title">
    <div className="panel-heading"><div><p className="eyebrow">车辆故障智能接替</p><h2 id="fleet-allocation-title">替代车辆调度计算</h2></div><Truck size={18}/></div>
    <div className="fleet-transfer" aria-label="故障车辆到接替车辆">
      <article className="fleet-transfer-card is-original"><span>故障车辆</span><strong>{evidence(allocation.original_vehicle_id)}</strong></article>
      <div className="fleet-transfer-arrow"><ArrowRight aria-hidden="true"/><span>{!hasReplacement ? "无可用接替车辆" : pickupDistance !== null && pickupMinutes !== null ? `接驳 ${pickupDistance} 公里 · ${pickupMinutes} 分钟` : "接驳路线待复核"}</span></div>
      <article className="fleet-transfer-card is-selected"><span>接替车辆</span><strong>{hasReplacement ? evidence(allocation.target_vehicle_id) : "无可用接替车辆"}</strong><span className="fleet-driver"><UserRound size={13}/>司机 {hasReplacement ? allocation.target_driver_id ?? "未分配" : "未分配"}</span>{selectedRank ? <span className="fleet-rank-result">综合排名第 {selectedRank}</span> : null}</article>
    </div>
    <div className="fleet-score-summary"><span>入选评分</span><strong>{evidence(selected?.score)}</strong><small>评分公式：{evidence(allocation.scoring_formula)}</small></div>
    <ScoreComponents components={selected?.score_components ?? null}/>
    <div className="fleet-candidate-heading"><h3>全部候选车辆</h3><span>候选 {allocation.candidate_vehicles.length} 辆 · 可调度 {ranking.eligible.length} 辆 · 已排除 {allocation.candidate_vehicles.length - ranking.eligible.length} 辆</span></div>
    <div className="fleet-candidate-table-wrap">
      <table className="fleet-candidate-table">
        <caption>车辆候选证据表：逐车核对资格、接驳与评分依据</caption>
        <thead><tr>
          <th scope="col">车辆</th><th scope="col">综合排名</th><th scope="col">资格与原因</th><th scope="col">司机</th><th scope="col">车辆状态</th><th scope="col">剩余载重</th><th scope="col">车辆证据</th><th scope="col">接驳距离</th><th scope="col">接驳时间</th><th scope="col">评分</th><th scope="col">评分分项</th>
        </tr></thead>
        <tbody>{ranking.displayCandidates.map((candidate) => {
          const isSelected = candidate.vehicle_id === allocation.target_vehicle_id;
          return <tr
            key={candidate.vehicle_id}
            className={`fleet-candidate ${isSelected ? "is-selected" : candidate.eligible ? "is-eligible" : "is-excluded"}`}
            data-vehicle-id={candidate.vehicle_id}
            aria-label={`${candidate.vehicle_id} 候选车辆`}
          >
            <th scope="row">{candidate.vehicle_id}</th><td data-field="rank">{rankEvidence(candidate, ranking.rankByVehicleId.get(candidate.vehicle_id))}</td>
            <td data-field="eligibility"><strong>{eligibilityLabel(candidate, allocation.target_vehicle_id)}</strong><ul>{candidateDecision(candidate, allocation.target_vehicle_id).map((reason) => <li key={reason}>{reason}</li>)}</ul></td>
            <td data-field="driver"><strong>{candidate.driver_id ?? "未分配"}</strong><small>{localizedEvidenceStatus(candidate.driver_status, candidate.driver_id ? "状态未记录" : "无可用司机")}</small></td>
            <td data-field="vehicle-status">{localizedEvidenceStatus(candidate.vehicle_status)}</td>
            <td data-field="remaining-capacity">{evidenceWithUnit(candidate.remaining_capacity_kg, "千克")}</td>
            <td data-field="vehicle-evidence"><span>总重 {evidenceWithUnit(candidate.gross_weight_tons, "吨")}</span><span>能力 {evidence(candidate.cargo_capability)}</span></td>
            <td data-field="pickup-distance">{pickupEvidence(candidate, candidate.pickup_distance_km, "公里")}</td>
            <td data-field="pickup-eta">{pickupEvidence(candidate, candidate.pickup_eta_minutes, "分钟")}</td>
            <td data-field="score">{scoreEvidence(candidate)}</td>
            <td data-field="score-components"><ScoreComponents components={candidate.score_components} className="fleet-candidate-score-components"/></td>
          </tr>;
        })}</tbody>
      </table>
    </div>
  </section>;
}