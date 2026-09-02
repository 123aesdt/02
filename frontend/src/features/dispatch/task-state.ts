export interface TaskStateCopy {
  title: string;
  description: string;
}

const stateCopy: Record<string, TaskStateCopy> = {
  PENDING: { title: "任务已接收", description: "任务已接收，等待 Worker 处理。" },
  PROCESSING: { title: "AI 调度处理中", description: "八个 Agent 正在异步生成调度决策。" },
  COMPLETED: { title: "调度已完成", description: "调度与审核结果已持久化。" },
  REVIEW_REQUIRED: { title: "人工复核", description: "该任务需要运营人员人工复核。" },
  TASK_NOT_FOUND: { title: "未找到任务", description: "未找到该调度任务。" },
  QUEUE_UNAVAILABLE: { title: "队列不可用", description: "调度队列暂时不可用，请稍后重试。" },
  IDEMPOTENCY_CONFLICT: { title: "提交冲突", description: "该请求已与其他调度任务关联。" },
  BACKEND_OFFLINE: { title: "后端服务离线", description: "后端服务暂时不可达。" },
};

export function taskStateCopy(status: string): TaskStateCopy {
  return stateCopy[status] ?? { title: "服务暂不可用", description: "暂时无法读取调度任务，请稍后重试。" };
}
