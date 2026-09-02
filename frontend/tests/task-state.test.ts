import { describe, expect, it } from "vitest";

import { taskStateCopy } from "../src/features/dispatch/task-state";

describe("Task status presentation", () => {
  it("maps a pending API task to an honest waiting state", () => {
    expect(taskStateCopy("PENDING")).toMatchObject({ title: "任务已接收", description: "任务已接收，等待 Worker 处理。" });
  });

  it("maps review and queue failures to safe business copy", () => {
    expect(taskStateCopy("REVIEW_REQUIRED").title).toBe("人工复核");
    expect(taskStateCopy("QUEUE_UNAVAILABLE").description).toBe("调度队列暂时不可用，请稍后重试。");
    expect(taskStateCopy("BACKEND_OFFLINE").title).toBe("后端服务离线");
  });
});
