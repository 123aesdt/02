import { localizeStatus } from "../../utils/presentation-labels";

type StatusTone = "brand" | "success" | "warning" | "danger" | "info" | "neutral";

const STATUS_PRESENTATION: Record<string, { label: string; tone: StatusTone; marker: string }> = {
  APPROVED: { label: "已批准", tone: "success", marker: "✓" },
  COMPLETED: { label: "完成", tone: "success", marker: "✓" },
  LIVE: { label: "实时", tone: "success", marker: "●" },
  RUNNING: { label: "运行中", tone: "brand", marker: "▶" },
  REVIEW_REQUIRED: { label: "需复核", tone: "warning", marker: "!" },
  DEGRADED: { label: "降级", tone: "warning", marker: "!" },
  STALE: { label: "数据陈旧", tone: "warning", marker: "◷" },
  FAILED: { label: "失败", tone: "danger", marker: "×" },
  ERROR: { label: "异常", tone: "danger", marker: "×" },
  OFFLINE: { label: "离线", tone: "danger", marker: "×" },
  EXPIRED: { label: "已过期", tone: "danger", marker: "×" },
  UNAVAILABLE: { label: "不可用", tone: "danger", marker: "×" },
  VERIFIED: { label: "已验证", tone: "info", marker: "◆" },
  WAITING: { label: "等待", tone: "neutral", marker: "•" },
  NOT_EXPOSED: { label: "未开放", tone: "neutral", marker: "—" },
  NO_PERMISSION: { label: "无权限", tone: "neutral", marker: "—" },
};

export interface StatusBadgeProps {
  status: string;
  label?: string;
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const canonical = status.trim().toUpperCase();
  const presentation = STATUS_PRESENTATION[canonical] ?? {
    label: label ?? localizeStatus(status),
    tone: "info" as const,
    marker: "•",
  };

  return <span
    className="ui-status-badge"
    data-tone={presentation.tone}
    aria-label={`${label ?? presentation.label}（${canonical}）`}
  >
    <span className="ui-status-badge__marker" aria-hidden="true">{presentation.marker}</span>
    <span>{label ?? presentation.label}</span>
  </span>;
}
