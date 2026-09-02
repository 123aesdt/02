import { useEffect, useState } from "react";

import { runtimeConfig } from "../config/runtime";
import { ApiError } from "../services/api/client";
import { getTaskResult, getTaskStatus, type TaskResultResponse, type TaskStatusResponse } from "../services/dispatch-service";

const terminalStatuses = new Set(["COMPLETED", "REVIEW_REQUIRED"]);

interface TaskApiState {
  status: TaskStatusResponse | null;
  result: TaskResultResponse | null;
  error: ApiError | null;
  loading: boolean;
}

export function useTaskApi(taskId: string, refreshKey = 0): TaskApiState {
  const [state, setState] = useState<TaskApiState>({ status: null, result: null, error: null, loading: runtimeConfig.dataMode === "api" });

  useEffect(() => {
    if (runtimeConfig.dataMode !== "api") return undefined;
    const controller = new AbortController();
    let timer: number | undefined;
    const load = async () => {
      try {
        const status = await getTaskStatus(taskId, controller.signal);
        const result = terminalStatuses.has(status.status) ? await getTaskResult(taskId, controller.signal) : null;
        setState({ status, result, error: null, loading: false });
        if (!terminalStatuses.has(status.status)) timer = window.setTimeout(() => void load(), 1000);
      } catch (error) {
        if (controller.signal.aborted) return;
        setState({ status: null, result: null, error: error instanceof ApiError ? error : new ApiError(0, "BACKEND_OFFLINE", "后端服务不可达。"), loading: false });
      }
    };
    void load();
    return () => {
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [taskId, refreshKey]);

  return state;
}
