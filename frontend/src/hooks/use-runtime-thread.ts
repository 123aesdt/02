import { useEffect, useState } from "react";

import { runtimeThreadClient, type RuntimeThreadClient } from "../services/api/runtime-thread-client";
import type { RuntimeThreadDetail, RuntimeThreadHistory } from "../types/runtime-thread";

export type RuntimeThreadViewState =
  | { kind: "disabled" }
  | { kind: "loading" }
  | { kind: "ready"; detail: RuntimeThreadDetail; history: RuntimeThreadHistory }
  | { kind: "unauthorized" }
  | { kind: "unavailable" };

export function useRuntimeThread(
  taskId: string,
  enabled: boolean,
  client: RuntimeThreadClient = runtimeThreadClient,
  refreshKey = 0,
): RuntimeThreadViewState {
  const [result, setResult] = useState<{
    requestKey: string;
    state: Extract<RuntimeThreadViewState, { kind: "ready" | "unauthorized" | "unavailable" }>;
  } | null>(null);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    void client.getByTask(taskId, controller.signal).then(async (detail) => {
      const history = await client.getHistory(detail.thread_id, 20, controller.signal);
      if (!controller.signal.aborted) setResult({ requestKey: `${taskId}:${refreshKey}`, state: { kind: "ready", detail, history } });
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return;
      const status = typeof error === "object" && error !== null && "status" in error ? error.status : undefined;
      setResult({ requestKey: `${taskId}:${refreshKey}`, state: { kind: status === 403 ? "unauthorized" : "unavailable" } });
    });
    return () => controller.abort();
  }, [client, enabled, refreshKey, taskId]);

  if (!enabled) return { kind: "disabled" };
  return result?.requestKey === `${taskId}:${refreshKey}` ? result.state : { kind: "loading" };
}
