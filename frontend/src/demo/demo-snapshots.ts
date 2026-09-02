export interface DemoRuntimeConfig {
  dataMode: "mock" | "api";
  authenticationMode?: "development_jwt" | "oidc_jwt";
}

export interface DemoAgentSnapshot {
  id: string;
  name: string;
  status: string;
  latency: string;
  detail: string;
  role: string;
  input: string;
}

export const DEMO_TASK_ID = "DEMO-TASK-001";

export function isDemoSnapshotEnabled(config: DemoRuntimeConfig): boolean {
  return config.dataMode === "mock" || config.authenticationMode === "development_jwt";
}

export const demoCapabilitySummaries = {
  智能体: "8 个智能体已准备，可展示完整协作链路。",
  记忆: "50 条向量验收记录、24 条关系事实可供演示。",
  可观测性: "提供 11 项有界遥测样本与趋势预览。",
  治理与安全: "32 条审计样本，高风险任务保留人工复核。",
} as const;

export const demoAgentSnapshots: readonly DemoAgentSnapshot[] = [
  { id: "intake", name: "接入智能体", status: "SUCCESS", latency: "12 ms", detail: "已规范化县域配送异常，并建立演示调度上下文。", role: "规范调度上下文", input: "任务与异常载荷" },
  { id: "entity_memory", name: "实体记忆智能体", status: "SUCCESS", latency: "42 ms", detail: "召回雨天绕行历史方案，匹配李师傅与新平路场景。", role: "语义长期记忆召回", input: "司机、路线与异常文本" },
  { id: "graph_memory", name: "图记忆智能体", status: "SUCCESS", latency: "18 ms", detail: "找到 5 条有界关系事实和 2 条可解释路径。", role: "有界关系召回", input: "类型化实体引用" },
  { id: "environment", name: "环境智能体", status: "FALLBACK", latency: "811 ms", detail: "模拟道路湿滑风险，采用静态安全规则完成降级。", role: "环境风险评估", input: "路线与当前环境" },
  { id: "capacity", name: "运力智能体", status: "SUCCESS", latency: "18 ms", detail: "演示车辆与司机可用，装载量处于安全范围。", role: "运力约束检查", input: "车辆运行状态" },
  { id: "routing", name: "路径智能体", status: "SUCCESS", latency: "31 ms", detail: "比较 3 条候选路线，推荐 102 国道安全绕行。", role: "路线推荐", input: "记忆、环境与运力" },
  { id: "dispatch", name: "调度智能体", status: "SUCCESS", latency: "27 ms", detail: "生成演示调度版本 1，并准备发布给接收员工。", role: "持久化调度", input: "最终路线决策" },
  { id: "audit", name: "审核智能体", status: "APPROVED", latency: "14 ms", detail: "路线、记忆、降级和发布证据均通过演示审核。", role: "证据审核", input: "最终图状态" },
] as const;

export const demoObservabilityMetrics: Readonly<Record<string, number>> = {
  http_qps: 0.32,
  http_p95: 0.086,
  http_error_rate: 0.003,
  agent_p95: 0.238,
  worker_pending: 0,
  worker_lag: 1,
  graph_p95: 0.018,
  checkpoint_p95: 0.026,
  override_success: 0.967,
  memory_partial: 2,
  dependency_up: 4,
};

export function mergeObservabilityMetrics(
  liveMetrics: Record<string, number | null> | null | undefined,
  enabled: boolean,
): { metrics: Record<string, number | null>; demoKeys: string[] } {
  const metrics = { ...(liveMetrics ?? {}) };
  if (!enabled) return { metrics, demoKeys: [] };

  const demoKeys: string[] = [];
  for (const [key, value] of Object.entries(demoObservabilityMetrics)) {
    if (metrics[key] == null) {
      metrics[key] = value;
      demoKeys.push(key);
    }
  }
  return { metrics, demoKeys };
}
