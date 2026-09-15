import type { AgentEvidence, AgentWork } from "../types/dispatch";
import type { TaskEvent } from "../types/task-events";

type Data = Record<string, unknown>;

const definitions: Record<string, { input: string; action: string }> = {
  intake: {
    input: "任务、车辆、起终点和异常描述",
    action: "校验任务字段，建立标准调度上下文",
  },
  entity_memory: {
    input: "车辆、路线与异常特征",
    action: "检索相似历史事件及其处置方案",
  },
  graph_memory: {
    input: "司机、车辆、路线等实体关系",
    action: "召回关系事实与可解释路径",
  },
  environment: {
    input: "当前路线和外部环境服务",
    action: "评估天气、道路状态与环境风险",
  },
  capacity: {
    input: "司机、车辆、载重和候选车队",
    action: "核验当前运力并筛选可执行车辆",
  },
  routing: {
    input: "阻断道路、运力、记忆和路网快照",
    action: "比较候选路线并检查道路连通性",
  },
  dispatch: {
    input: "最终车辆和路线决策",
    action: "持久化调度结果并生成执行版本",
  },
  audit: {
    input: "路线、运力、降级和调度证据",
    action: "逐项审核并决定是否自动发布",
  },
};

function record(value: unknown): Data | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Data : undefined;
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function number(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function texts(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function rows(value: unknown): Data[] {
  return Array.isArray(value) ? value.map(record).filter((item): item is Data => Boolean(item)) : [];
}

function evidence(label: string, value: unknown): AgentEvidence | undefined {
  if (typeof value === "boolean") return { label, value: value ? "是" : "否" };
  if (typeof value === "number") return { label, value: String(value) };
  const normalized = text(value);
  return normalized ? { label, value: normalized } : undefined;
}

function compact(items: Array<AgentEvidence | undefined>): AgentEvidence[] {
  return items.filter((item): item is AgentEvidence => Boolean(item)).slice(0, 5);
}

function translate(value: unknown): string {
  const raw = text(value);
  if (!raw) return "未知";
  const labels: Record<string, string> = {
    rain: "降雨",
    sunny: "晴朗",
    blocked: "道路阻断",
    normal: "道路正常",
    high: "高",
    medium: "中",
    low: "低",
  };
  return labels[raw.toLowerCase()] ?? raw;
}

function startedResult(action: string): string {
  return `正在执行：${action}`;
}

function intake(data: Data) {
  const vehicle = text(data.vehicle_id);
  const blocked = texts(data.affected_edge_ids);
  const result = vehicle
    ? `已规范化异常并锁定车辆 ${vehicle}${blocked.length ? `，识别阻断道路 ${blocked.join("、")}` : ""}`
    : "已校验任务并建立标准调度上下文";
  return {
    result,
    evidence: compact([
      evidence("车辆", vehicle),
      evidence("起终点", text(data.origin_node_id) && text(data.destination_node_id)
        ? `${text(data.origin_node_id)} → ${text(data.destination_node_id)}`
        : undefined),
      evidence("阻断道路", blocked.join("、")),
      evidence("沙盘上下文", data.sandtable_context_loaded),
    ]),
  };
}

function entityMemory(data: Data) {
  const memories = rows(data.memory_results);
  const best = memories[0];
  const similarity = number(best?.similarity_score);
  return {
    result: memories.length
      ? `召回 ${memories.length} 条历史处置记忆${similarity === undefined ? "" : `，最高相似度 ${Math.round(similarity * 100)}%`}`
      : "未找到可复用历史记忆，继续使用当前任务证据",
    evidence: compact([
      evidence("记忆 ID", best?.memory_id),
      evidence("历史路线", best?.route_id),
      evidence("历史处置", best?.historical_resolution),
    ]),
  };
}

function graphMemory(data: Data) {
  const facts = rows(data.graph_memory_facts);
  const paths = rows(data.graph_memory_paths);
  const degraded = text(data.graph_memory_error);
  return {
    result: degraded
      ? "图记忆暂不可用，已降级为当前任务证据"
      : `召回 ${facts.length} 条关系事实和 ${paths.length} 条可解释路径`,
    evidence: compact([
      evidence("启用图记忆", data.graph_memory_used),
      evidence("关系事实", `${facts.length} 条`),
      evidence("关系路径", `${paths.length} 条`),
      evidence("降级原因", degraded),
    ]),
  };
}

function environment(data: Data) {
  const fallback = data.fallback_used === true;
  const risk = translate(data.environment_risk);
  return {
    result: fallback
      ? `环境服务已降级，使用静态路况继续规划，风险 ${risk}`
      : `识别${translate(data.weather)}、${translate(data.road_condition)}，环境风险 ${risk}`,
    evidence: compact([
      evidence("天气", translate(data.weather)),
      evidence("道路", translate(data.road_condition)),
      evidence("风险", risk),
      evidence("数据源", data.environment_provider),
      evidence("降级原因", data.fallback_reason),
    ]),
  };
}

function capacity(data: Data) {
  const selectedVehicle = text(data.selected_vehicle_id) ?? text(data.vehicle_id);
  const selectedDriver = text(data.selected_driver_id);
  const candidates = rows(data.candidate_vehicles);
  const reassigned = data.vehicle_reassigned === true;
  const result = reassigned
    ? `比较 ${candidates.length} 辆候选车，选择 ${selectedVehicle ?? "可用车辆"}${selectedDriver ? ` / ${selectedDriver}` : ""}`
    : selectedVehicle
      ? `已确认车辆 ${selectedVehicle} 具备继续执行条件`
      : "已完成司机、车辆和载重约束校验";
  return {
    result,
    evidence: compact([
      evidence("选定车辆", selectedVehicle),
      evidence("选定司机", selectedDriver),
      evidence("候选车辆", candidates.length ? `${candidates.length} 辆` : undefined),
      evidence("车辆可用", data.vehicle_available),
      evidence("运力状态", data.capacity_status),
    ]),
  };
}

function routing(data: Data) {
  const route = text(data.recommended_route);
  const path = record(data.recommended_path);
  const blocked = texts(data.blocked_edge_ids);
  const distance = path?.distance_km;
  const eta = path?.estimated_minutes;
  const result = route
    ? `已${blocked.length ? `避开 ${blocked.join("、")}，` : ""}推荐路线 ${route}`
    : text(data.decision_reason) ?? "未生成可执行路线";
  return {
    result,
    evidence: compact([
      evidence("推荐路线", route),
      evidence("预计里程", distance === undefined || distance === null ? undefined : `${distance} 公里`),
      evidence("预计用时", eta === undefined || eta === null ? undefined : `${eta} 分钟`),
      evidence("避开道路", blocked.join("、")),
      evidence("算法", data.algorithm),
    ]),
  };
}

function dispatch(data: Data) {
  const vehicle = text(data.target_vehicle_id);
  const route = text(data.target_route_id);
  const executed = data.executed === true;
  return {
    result: executed
      ? `调度已执行：${vehicle ?? "目标车辆"} 将按 ${route ?? "推荐路线"} 行驶`
      : "调度结果已生成，尚未标记为已执行",
    evidence: compact([
      evidence("目标车辆", vehicle),
      evidence("目标司机", data.target_driver_id),
      evidence("目标路线", route),
      evidence("执行版本", data.version),
      evidence("执行状态", data.status),
    ]),
  };
}

function audit(data: Data) {
  const auditData = record(data.audit_result) ?? data;
  const checks = record(auditData.checks) ?? {};
  const entries = Object.entries(checks);
  const passedCount = entries.filter(([, value]) => value === true).length;
  const approved = auditData.passed === true || text(auditData.audit_status) === "APPROVED";
  return {
    result: approved
      ? `${passedCount || entries.length} 项校验通过，允许自动发布`
      : text(auditData.reason) ?? "审核未通过，需要复核调度证据",
    evidence: compact([
      evidence("审核结论", auditData.audit_status),
      evidence("通过检查", entries.length ? `${passedCount} / ${entries.length}` : undefined),
      evidence("调度记录", auditData.dispatch_id),
      evidence("审计记录", auditData.audit_record_id),
      evidence("需要人工复核", auditData.requires_manual_review),
    ]),
  };
}

const presenters: Record<string, (data: Data) => { result: string; evidence: AgentEvidence[] }> = {
  intake,
  entity_memory: entityMemory,
  graph_memory: graphMemory,
  environment,
  capacity,
  routing,
  dispatch,
  audit,
};

export function buildAgentWork(agentId: string, event: TaskEvent): AgentWork {
  const definition = definitions[agentId] ?? {
    input: "任务上下文",
    action: "处理当前任务事件",
  };
  const presentation = event.event_type.endsWith("_STARTED")
    ? { result: startedResult(definition.action), evidence: [] }
    : (presenters[agentId]?.(event.data) ?? {
      result: "已完成当前节点处理",
      evidence: [],
    });
  return {
    ...definition,
    ...presentation,
    eventType: event.event_type,
    eventId: event.event_id,
  };
}

export function formatAgentElapsed(startedAt: string | undefined, completedAt: string): string {
  if (!startedAt) return "—";
  const milliseconds = Date.parse(completedAt) - Date.parse(startedAt);
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return "—";
  if (milliseconds < 1000) return `${Math.max(1, Math.round(milliseconds))} ms`;
  return `${(milliseconds / 1000).toFixed(2)} s`;
}
