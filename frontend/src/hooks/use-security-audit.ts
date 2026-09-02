import { useEffect, useState } from "react";

import { runtimeConfig } from "../config/runtime";
import {
  createSecurityAuditClient,
  SecurityAuditApiError,
  type SecurityAuditEvent,
} from "../services/api/security-audit-client";
import type { ReadState } from "../types/workspace";

const client = createSecurityAuditClient({ baseUrl: runtimeConfig.apiBaseUrl });
const nonApiState: ReadState<SecurityAuditEvent[]> = {
  state: "NOT_EXPOSED",
  data: null,
  message: "演示模式不生成安全审计事件。",
};

export function useSecurityAudit(): ReadState<SecurityAuditEvent[]> {
  const [state, setState] = useState<ReadState<SecurityAuditEvent[]>>({ state: "LOADING", data: null });

  useEffect(() => {
    if (runtimeConfig.dataMode !== "api") return undefined;
    const controller = new AbortController();
    void client.listRecent(controller.signal).then((items) => {
      setState(items.length > 0 ? { state: "READY", data: items } : { state: "EMPTY", data: null });
    }, (error: unknown) => {
      if (controller.signal.aborted) return;
      setState(error instanceof SecurityAuditApiError && error.status === 403
        ? { state: "FORBIDDEN", data: null }
        : { state: "UNAVAILABLE", data: null });
    });
    return () => controller.abort();
  }, []);

  return runtimeConfig.dataMode === "api" ? state : nonApiState;
}
