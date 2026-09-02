import { ApiError } from "../../services/api/client";
import type { OverrideSubmissionState } from "../../types/runtime-override";

const messages: Record<string, { state: OverrideSubmissionState; message: string }> = {
  RUNTIME_OVERRIDE_FORBIDDEN: { state: "REJECTED", message: "无权限执行运行态强干预" },
  RUNTIME_STATE_VERSION_CONFLICT: { state: "CONFLICT", message: "运行状态已变化，请刷新后重试" },
  RUNTIME_OVERRIDE_BUSY: { state: "BUSY", message: "当前 Thread 正在被其他操作修改" },
  THREAD_NOT_STABLE: { state: "BUSY", message: "当前 Agent 正在执行，暂不可干预" },
  THREAD_TERMINAL: { state: "REJECTED", message: "任务已经结束，不能修改运行状态" },
  RUNTIME_STATE_PRECONDITION_FAILED: { state: "CONFLICT", message: "您看到的状态已过期" },
  OVERRIDE_FIELD_NOT_ALLOWED: { state: "REJECTED", message: "该修改不被系统允许" },
  OVERRIDE_VALUE_INVALID: { state: "REJECTED", message: "该修改不被系统允许" },
  CHECKPOINT_STORE_UNAVAILABLE: { state: "FAILED", message: "运行态存储暂不可用；可重试同一操作" },
};

export function runtimeOverrideError(error: unknown): { state: OverrideSubmissionState; message: string } {
  if (error instanceof ApiError) return messages[error.code] ?? { state: "FAILED", message: "运行时干预请求失败" };
  return { state: "FAILED", message: "网络不可用；结果可能未知，请重试同一操作" };
}
