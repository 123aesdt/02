const STATUS_LABELS: Record<string, string> = {
  ACTIVE: "已生效",
  APPLIED: "已应用",
  ALLOWED: "允许",
  APPROVED: "已批准",
  ASSIGNED: "已分配",
  AVAILABLE: "可用",
  BROKEN: "故障",
  CHECKING: "检查中",
  CANCELLED: "已取消",
  COMPLETED: "已完成",
  CONFLICT: "冲突",
  CONFLICT_REVIEW: "冲突复核",
  CONFIGURED: "已配置",
  CONNECTED: "已连接",
  CONNECTING: "正在连接",
  DEGRADED: "已降级",
  DEMO: "演示",
  DEMO_DATA: "演示数据",
  DOWN: "异常",
  DISCONNECTED: "未连接",
  ELIGIBLE: "可干预",
  FAILED: "失败",
  FALLBACK: "已降级",
  FINALIZING: "正在完成",
  HUMAN_CONFIRMED: "人工确认",
  HIGH: "高",
  IDLE: "待操作",
  IN_PROGRESS: "处理中",
  LIVE: "实时",
  LOW: "低",
  MAINTENANCE: "维护中",
  MEDIUM: "中",
  NORMAL: "正常",
  NEW_FACT: "新事实",
  NOT_REQUIRED: "无需执行",
  NOT_STABLE: "运行中，不可干预",
  NOT_EXPOSED: "未开放",
  NO_PERMISSION: "无权限",
  OFFLINE: "离线",
  PARTIAL: "部分完成",
  PENDING: "等待中",
  PUBLISHED: "已发布",
  QUEUED: "排队中",
  PROCESSING: "处理中",
  REPLACE: "替换",
  CREATE: "创建",
  RECOMMENDED: "推荐",
  REJECTED: "已拒绝",
  REVIEW_REQUIRED: "需要复核",
  RUNNING: "运行中",
  SAFE: "安全",
  STABLE: "稳定",
  STAGED: "暂存",
  STALE: "数据陈旧",
  SUBMITTING: "提交中",
  SUCCESS: "成功",
  SUCCEEDED: "已完成",
  TERMINAL: "已结束",
  UNAVAILABLE: "不可用",
  UP: "正常",
  VERIFIED: "已验证",
  WAITING: "等待中",
};

const FIELD_LABELS: Record<string, string> = {
  status: "状态",
};

const AUDIT_CHECK_LABELS: Record<string, string> = {
  route_consistency: "路线一致性",
  memory_consistency: "记忆一致性",
  fallback_consistency: "降级一致性",
  dispatch_execution: "调度执行",
};

const DISPLAY_TEXT_LABELS: Record<string, string> = {
  "All evidence persisted": "所有证据已持久化",
  "Vehicle capacity unavailable": "车辆运力不可用",
  "Vehicle runtime status is BROKEN.": "车辆运行状态为故障。",
};

const NODE_LABELS: Record<string, string> = {
  intake: "接入",
  entity_memory: "实体记忆",
  graph_memory: "图记忆",
  environment: "环境",
  capacity: "运力",
  routing: "路径规划",
  dispatch: "调度",
  audit: "审核",
  END: "结束",
};

const ENTITY_LABELS: Record<string, string> = {
  Anomaly: "异常",
  Driver: "司机",
  Resolution: "解决方案",
  Route: "路线",
  Vehicle: "车辆",
  Weather: "天气",
};

const RELATION_LABELS: Record<string, string> = {
  ALTERNATIVE_TO: "可替代",
  DRIVES: "驾驶",
  HAS_RISK_ON: "存在风险",
  HIGH_RISK_WHEN: "特定条件下高风险",
  RESOLVED_BY: "解决方式",
};

export function localizeStatus(value: string | null | undefined): string {
  if (!value) return "—";
  return STATUS_LABELS[value.trim().toUpperCase().replaceAll(" ", "_")] ?? value;
}

export function localizeNode(value: string | null | undefined): string {
  if (!value) return "—";
  return NODE_LABELS[value] ?? value;
}

export function localizeEntityType(value: string | null | undefined): string {
  if (!value) return "—";
  return ENTITY_LABELS[value] ?? value;
}

export function localizeRelationType(value: string): string {
  return RELATION_LABELS[value] ?? value;
}

export function localizeRelationText(value: string): string {
  return Object.entries(RELATION_LABELS).reduce((text, [code, label]) => text.replaceAll(code, label), value);
}

export function localizeField(value: string | null | undefined): string {
  if (!value) return "—";
  return FIELD_LABELS[value] ?? value;
}

export function localizeAuditCheck(value: string): string {
  return AUDIT_CHECK_LABELS[value] ?? value;
}

export function localizeDisplayText(value: string | null | undefined): string {
  if (!value) return "—";
  if (DISPLAY_TEXT_LABELS[value]) return DISPLAY_TEXT_LABELS[value];
  return value
    .replace(/\bVehicle\b/g, "车辆")
    .replace(/\bBROKEN\b/g, "故障")
    .replace(/\bUNAVAILABLE\b/g, "不可用")
    .replace(/\bMAINTENANCE\b/g, "维护中")
    .replace(/\bNORMAL\b/g, "正常");
}
