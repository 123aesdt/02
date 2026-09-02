import { useEffect, useState } from "react";

import { runtimeOverrideClient, type RuntimeOverrideClient } from "../services/api/runtime-override-client";
import type { RuntimeOverrideHistory } from "../types/runtime-override";

export function useRuntimeOverrideHistory(
  threadId: string | null,
  enabled: boolean,
  client: RuntimeOverrideClient = runtimeOverrideClient,
  refreshKey = 0,
) {
  const [value, setValue] = useState<{ key: string; history: RuntimeOverrideHistory } | null>(null);
  useEffect(() => {
    if (!enabled || !threadId) return;
    const controller = new AbortController();
    void client.listByThread(threadId, 20, controller.signal).then((history) => {
      if (!controller.signal.aborted) setValue({ key: `${threadId}:${refreshKey}`, history });
    }).catch(() => undefined);
    return () => controller.abort();
  }, [client, enabled, refreshKey, threadId]);
  return value?.key === `${threadId}:${refreshKey}` ? value.history : null;
}
