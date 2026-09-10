import { Route as RouteIcon } from "lucide-react";

import type { PathResponse, RoutePlanResponse } from "../services/api/dispatch-adapter";
import { localizeStatus } from "../utils/presentation-labels";
import { RouteVisual } from "./route-visual";

function algorithmName(value: string): string {
  return value === "DIJKSTRA_V1" ? "Dijkstra（DIJKSTRA_V1）" : value;
}

function sequence(values: string[]): string {
  return values.length ? values.join(" → ") : "暂无";
}

function signedDecimal(value: string | null): string {
  if (value === null) return "—";
  return value.startsWith("-") || value.startsWith("+") ? value : `+${value}`;
}

function signedInteger(value: number | null): string {
  if (value === null) return "—";
  return value > 0 ? `+${value}` : String(value);
}

function PathSummary({ label, path }: { label: string; path: PathResponse | null }) {
  return <article className="route-path-summary">
    <h3>{label}</h3>
    {path ? <>
      <strong>{path.distance_km} 公里 · {path.estimated_minutes} 分钟</strong>
      <dl>
        <div><dt>节点序列</dt><dd>{sequence(path.node_ids)}</dd></div>
        <div><dt>道路序列</dt><dd>{sequence(path.edge_ids)}</dd></div>
        <div><dt>风险代价</dt><dd>{path.risk_cost}</dd></div>
      </dl>
    </> : <p>暂无路线证据</p>}
  </article>;
}

export function RoutePlanResultPanel({ routePlan, pickupEdgeIds = [] }: { routePlan: RoutePlanResponse; pickupEdgeIds?: string[] }) {
  const blockedEdges = sequence(routePlan.blocked_edge_ids);
  const recommendedPath = routePlan.recommended_path;
  const recommendedEdgeCount = recommendedPath?.edge_ids.length ?? 0;
  const avoidedBlockedEdges = recommendedPath
    ? routePlan.blocked_edge_ids.filter((edgeId) => !recommendedPath.edge_ids.includes(edgeId))
    : [];
  return <section className="route-plan-result-panel" aria-labelledby="route-plan-result-title">
    <div className="panel-heading"><div><p className="eyebrow">道路堵塞重新计算</p><h2 id="route-plan-result-title">新路线规划计算</h2></div><RouteIcon size={18}/></div>
    <div className="route-calculation-strip" aria-label="路线计算摘要">
      <span><small>算法</small><strong>{algorithmName(routePlan.algorithm)}</strong></span>
      <span><small>道路网络</small><strong>{routePlan.road_network_version === null ? "网络版本未生成" : `网络版本 ${routePlan.road_network_version}`}</strong></span>
      <span><small>异常道路</small><strong>{routePlan.blocked_edge_ids.length ? `堵塞边 ${routePlan.blocked_edge_ids.join("、")}` : "无堵塞边"}</strong></span>
      <span><small>搜索范围</small><strong>{routePlan.visited_node_count === null ? "访问节点 —" : `访问节点 ${routePlan.visited_node_count} 个`}</strong></span>
    </div>
    <ol className="route-computation-steps" aria-label="路线重新计算步骤">
      <li><span>1</span><div><strong>读取虚拟道路网络</strong><small>{routePlan.network_nodes.length} 个节点 · {routePlan.network_edges.length} 条道路</small></div></li>
      <li><span>2</span><div><strong>应用异常约束</strong><small>{routePlan.blocked_edge_ids.length ? `封锁 ${blockedEdges}` : "没有封锁道路"}</small></div></li>
      <li><span>3</span><div><strong>执行 Dijkstra 搜索</strong><small>{routePlan.visited_node_count === null ? "访问节点数暂无" : `访问 ${routePlan.visited_node_count} 个节点`}</small></div></li>
      <li><span>4</span><div><strong>输出新路线</strong><small>{routePlan.recommended_path ? `${recommendedEdgeCount} 条道路 · ${routePlan.recommended_path.distance_km} 公里` : "没有可用路线"}</small></div></li>
    </ol>
    <RouteVisual routePlan={routePlan} pickupEdgeIds={pickupEdgeIds}/>
    <div className="route-map-legend" aria-label="路线图例"><span data-legend="blocked">堵塞道路</span><span data-legend="pickup">接驳路线</span><span data-legend="recommended">新规划路线</span><span data-legend="original">原路线</span><span data-legend="normal">普通道路</span></div>
    <div className="route-paths"><PathSummary label="原路线" path={routePlan.original_path}/><PathSummary label="重新计算路线" path={routePlan.recommended_path}/></div>
    <div className="route-deltas"><span><small>里程变化</small><strong>{signedDecimal(routePlan.distance_delta_km)} 公里</strong></span><span><small>耗时变化</small><strong>{signedInteger(routePlan.eta_delta_minutes)} 分钟</strong></span><span><small>计算状态</small><strong>{localizeStatus(routePlan.routing_status)}</strong></span></div>
    <p className="route-avoidance-proof">{!routePlan.recommended_path ? "未找到可用新路线，需要人工复核" : avoidedBlockedEdges.length ? `已避开堵塞道路 ${sequence(avoidedBlockedEdges)}` : "新路线仍包含异常道路，请人工复核"}</p>
    <div className="route-candidate-targets"><h3>候选目标</h3>{routePlan.candidate_routes.length ? <ol>{routePlan.candidate_routes.map((candidate) => <li key={candidate.route_id} data-route-id={candidate.route_id}><span><strong>{candidate.route_name}</strong><small>{candidate.route_id} · {candidate.objective}</small></span><span>{candidate.distance_km} 公里 · {candidate.estimated_minutes} 分钟</span><b>{candidate.score} 分</b></li>)}</ol> : <p>暂无候选目标</p>}</div>
  </section>;
}
