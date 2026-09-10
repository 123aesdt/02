import { ArrowRight, BrainCircuit, CheckCircle2, ExternalLink, Route as RouteIcon, TriangleAlert, Truck } from "lucide-react";

import { resolveEvidenceScenario } from "../features/dispatch/evidence-scenario";
import type { RoutePlanResponse, VehicleAllocationResponse } from "../services/api/dispatch-adapter";

interface DispatchEvidenceOverviewProps {
  anomalyType?: string | null;
  vehicleAllocation?: VehicleAllocationResponse | null;
  routePlan?: RoutePlanResponse | null;
}

interface EvidenceStageProps {
  label: string;
  title: string;
  detail: string;
  icon: "input" | "compute" | "result" | "review";
}

interface ComparisonItemProps {
  label: string;
  value: string;
  detail: string;
  tone?: "danger" | "compute" | "success" | "review";
}

const STAGE_ICONS = {
  input: TriangleAlert,
  compute: BrainCircuit,
  result: CheckCircle2,
  review: TriangleAlert,
} as const;

function EvidenceStage({ label, title, detail, icon }: EvidenceStageProps) {
  const Icon = STAGE_ICONS[icon];
  return <li className={`evidence-stage is-${icon}`}>
    <span className="evidence-stage-icon"><Icon size={17} aria-hidden="true"/></span>
    <div><small>{label}</small><strong>{title}</strong><span>{detail}</span></div>
  </li>;
}

function FlowConnector() {
  return <li className="evidence-flow-connector" aria-hidden="true"><ArrowRight size={18}/></li>;
}

function ComparisonItem({ label, value, detail, tone = "compute" }: ComparisonItemProps) {
  return <li className={`evidence-comparison-item is-${tone}`}><small>{label}</small><strong>{value}</strong><span>{detail}</span></li>;
}

function selectedVehicle(allocation: VehicleAllocationResponse) {
  return allocation.candidate_vehicles.find((candidate) => candidate.vehicle_id === allocation.target_vehicle_id) ?? null;
}

function algorithmName(value: string): string {
  return value.startsWith("DIJKSTRA") ? "Dijkstra" : value || "路径算法";
}

function signedDecimal(value: string | null): string {
  if (value === null) return "里程变化未提供";
  return `${Number(value) > 0 ? "+" : ""}${value} 公里`;
}

function signedMinutes(value: number | null): string {
  if (value === null) return "耗时变化未提供";
  return `${value > 0 ? "+" : ""}${value} 分钟`;
}

function VehicleComparison({ allocation }: { allocation: VehicleAllocationResponse }) {
  const selected = selectedVehicle(allocation);
  const eligibleCount = allocation.candidate_vehicles.filter((candidate) => candidate.eligible === true).length;
  const excludedCount = allocation.candidate_vehicles.length - eligibleCount;
  const hasReplacement = allocation.vehicle_reassigned && Boolean(selected) && Boolean(allocation.target_vehicle_id);
  return <section className="evidence-comparison" aria-labelledby="vehicle-comparison-title">
    <div className="evidence-comparison-heading"><h4 id="vehicle-comparison-title">车辆调度计算对比</h4><span>选择结果来自运力评分证据</span></div>
    <ol>
      <ComparisonItem label="故障前" value={allocation.original_vehicle_id ?? "原车辆未提供"} detail="原执行车辆 · 已退出任务" tone="danger"/>
      <ComparisonItem label="筛选计算" value={`候选 ${allocation.candidate_vehicles.length} 辆`} detail={`可调度 ${eligibleCount} 辆 · 排除 ${excludedCount} 辆`}/>
      <ComparisonItem label="调度结果" value={hasReplacement ? `${allocation.target_vehicle_id} 接替` : "无可用接替车辆"} detail={hasReplacement ? `${allocation.target_vehicle_id} · ${allocation.target_driver_id ?? "司机待分配"} · ${selected?.score ?? "未提供"} 分` : "转入人工复核"} tone={hasReplacement ? "success" : "review"}/>
    </ol>
  </section>;
}

function RouteComparison({ routePlan }: { routePlan: RoutePlanResponse }) {
  const original = routePlan.original_path;
  const recommended = routePlan.recommended_path;
  const blockedEdges = routePlan.blocked_edge_ids.length ? routePlan.blocked_edge_ids.join("、") : "未标记道路";
  return <section className="evidence-comparison" aria-labelledby="route-comparison-title">
    <div className="evidence-comparison-heading"><h4 id="route-comparison-title">路线重规划计算对比</h4><span>对比异常约束应用前后路线</span></div>
    <ol>
      <ComparisonItem label="原路线" value={original ? `${original.distance_km} 公里 · ${original.estimated_minutes} 分钟` : "原路线未提供"} detail={original ? `${original.edge_ids.length} 条道路 · 包含异常边` : "缺少原路线证据"} tone="danger"/>
      <ComparisonItem label="Dijkstra 计算" value={`移除 ${blockedEdges}`} detail={routePlan.visited_node_count === null ? "访问节点数未提供" : `访问 ${routePlan.visited_node_count} 个节点`}/>
      <ComparisonItem label="新路线" value={recommended ? `${recommended.distance_km} 公里 · ${recommended.estimated_minutes} 分钟` : "未找到可用新路线"} detail={recommended ? `${signedDecimal(routePlan.distance_delta_km)} · ${signedMinutes(routePlan.eta_delta_minutes)}` : "转入人工复核"} tone={recommended ? "success" : "review"}/>
    </ol>
  </section>;
}

function VehicleEvidenceFlow({ allocation }: { allocation: VehicleAllocationResponse }) {
  const selected = selectedVehicle(allocation);
  const reassigned = allocation.vehicle_reassigned && Boolean(allocation.target_vehicle_id) && Boolean(selected);
  const candidateCount = allocation.candidate_vehicles.length;
  return <article className="evidence-scenario is-vehicle" aria-labelledby="vehicle-evidence-flow-title">
    <div className="evidence-scenario-heading"><span><Truck size={17} aria-hidden="true"/></span><div><small>车辆场景</small><h3 id="vehicle-evidence-flow-title">车辆故障处置</h3></div></div>
    <ol className="evidence-flow">
      <EvidenceStage icon="input" label="异常输入" title={`${allocation.original_vehicle_id ?? "原车辆"} 车辆故障`} detail="原执行车辆退出当前任务"/>
      <FlowConnector/>
      <EvidenceStage icon="compute" label="Agent 计算" title="运力智能体" detail={`比较 ${candidateCount} 辆候选车辆`}/>
      <FlowConnector/>
      <EvidenceStage icon={reassigned ? "result" : "review"} label="最终调度" title={reassigned ? `${allocation.target_vehicle_id} 接替` : "未找到可用接替车辆"} detail={reassigned ? `司机 ${allocation.target_driver_id ?? "待分配"} · 评分 ${selected?.score ?? "未提供"}` : "需要人工复核车辆调度"}/>
    </ol>
    <VehicleComparison allocation={allocation}/>
    <a className="evidence-anchor" href="#fleet-allocation-title">查看车辆计算依据<ExternalLink size={13} aria-hidden="true"/></a>
  </article>;
}

function RouteEvidenceFlow({ routePlan }: { routePlan: RoutePlanResponse }) {
  const blockedEdges = routePlan.blocked_edge_ids.length ? routePlan.blocked_edge_ids.join("、") : "未标记道路";
  const recommended = routePlan.recommended_path;
  const avoided = recommended ? routePlan.blocked_edge_ids.filter((edgeId) => !recommended.edge_ids.includes(edgeId)) : [];
  const visited = routePlan.visited_node_count === null ? "节点数未提供" : `访问 ${routePlan.visited_node_count} 个节点`;
  return <article className="evidence-scenario is-route" aria-labelledby="route-evidence-flow-title">
    <div className="evidence-scenario-heading"><span><RouteIcon size={17} aria-hidden="true"/></span><div><small>道路场景</small><h3 id="route-evidence-flow-title">道路堵塞重规划</h3></div></div>
    <ol className="evidence-flow">
      <EvidenceStage icon="input" label="异常输入" title={`${blockedEdges} 道路堵塞`} detail="堵塞道路从可行网络中移除"/>
      <FlowConnector/>
      <EvidenceStage icon="compute" label="Agent 计算" title="路径智能体" detail={`${algorithmName(routePlan.algorithm)} ${visited}`}/>
      <FlowConnector/>
      <EvidenceStage icon={recommended ? "result" : "review"} label="最终调度" title={recommended ? `新路线 ${recommended.distance_km} 公里` : "未找到可用新路线"} detail={avoided.length ? `已避开 ${avoided.join("、")}` : "需要人工复核异常道路"}/>
    </ol>
    <RouteComparison routePlan={routePlan}/>
    <a className="evidence-anchor" href="#route-plan-result-title">查看路线计算依据<ExternalLink size={13} aria-hidden="true"/></a>
  </article>;
}

function PresentationNavigation({ detailHref, detailLabel }: { detailHref: string; detailLabel: string }) {
  return <nav className="evidence-presentation-nav" aria-label="答辩讲解导航">
    <strong>答辩讲解导航</strong>
    <ol>
      <li><a href="#dispatch-evidence-overview-title"><span>1</span>处置总览</a></li>
      <li><a href={detailHref}><span>2</span>{detailLabel}</a></li>
      <li><a href="#agent-pipeline-title"><span>3</span>Agent 流水线</a></li>
    </ol>
  </nav>;
}

function EvidenceProvenance({ algorithm }: { algorithm: string }) {
  return <ul className="evidence-provenance" aria-label="计算证据来源">
    <li><strong>虚拟县域沙盘</strong><span>车辆、站点与道路均为演示数据</span></li>
    <li><strong>未接入高德地图</strong><span>本地道路网络独立计算</span></li>
    <li><strong>API 持久化结果</strong><span>刷新后仍可追溯复核</span></li>
    <li><strong>{algorithm}</strong><span>显示实际计算依据</span></li>
  </ul>;
}

export function DispatchEvidenceOverview({ anomalyType, vehicleAllocation, routePlan }: DispatchEvidenceOverviewProps) {
  const { vehicle: showVehicle, route: showRoute } = resolveEvidenceScenario(anomalyType, vehicleAllocation, routePlan);
  if (!showVehicle && !showRoute) return null;

  const vehicleTarget = showVehicle && vehicleAllocation?.vehicle_reassigned ? vehicleAllocation.target_vehicle_id : null;
  const routeDistance = showRoute ? routePlan?.recommended_path?.distance_km ?? null : null;
  const detailHref = showVehicle ? "#fleet-allocation-title" : "#route-plan-result-title";
  const detailLabel = showVehicle ? "车辆计算" : "路线计算";
  const algorithm = showRoute && routePlan ? `${algorithmName(routePlan.algorithm)} 算法` : vehicleAllocation?.scoring_formula ?? "运力评分规则";
  return <>
    <PresentationNavigation detailHref={detailHref} detailLabel={detailLabel}/>
    <section className="dispatch-evidence-overview" aria-labelledby="dispatch-evidence-overview-title">
      <header className="evidence-overview-heading"><div><p className="eyebrow">答辩关键证据 · API 持久化结果</p><h2 id="dispatch-evidence-overview-title">异常处置结果总览</h2><p>异常输入、Agent 计算过程与最终调度结果一屏对应。</p></div><span className="evidence-source"><CheckCircle2 size={14} aria-hidden="true"/>真实计算结果</span></header>
      <EvidenceProvenance algorithm={algorithm}/>
      <div className="evidence-scenarios">
        {showVehicle && vehicleAllocation ? <VehicleEvidenceFlow allocation={vehicleAllocation}/> : null}
        {showRoute && routePlan ? <RouteEvidenceFlow routePlan={routePlan}/> : null}
      </div>
      <section className="evidence-agent-chain" aria-labelledby="evidence-agent-chain-title">
        <h3 id="evidence-agent-chain-title">Agent 责任与输出</h3>
        <ul>
          <li><strong>运力智能体</strong><small>{showVehicle && vehicleAllocation ? `完成 ${vehicleAllocation.candidate_vehicles.length} 辆车辆筛选` : "本次异常无需换车"}</small></li>
          <li><strong>路径智能体</strong><small>{showRoute && routePlan ? `完成 ${algorithmName(routePlan.algorithm)} 重规划` : vehicleAllocation?.pickup_route ? "完成接替车辆接驳计算" : "沿用当前行驶路线"}</small></li>
          <li><strong>调度智能体</strong><small>{vehicleTarget ? `输出 ${vehicleTarget} 接替方案` : routeDistance ? `输出 ${routeDistance} 公里新路线` : "转入人工复核"}</small></li>
        </ul>
      </section>
    </section>
  </>;
}