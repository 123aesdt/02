import { useCallback, useEffect, useState } from "react";

import { runtimeConfig } from "../config/runtime";
import { createObservabilityClient, ObservabilityApiError } from "../services/api/observability-client";
import type { ObservabilityState, ObservabilitySummary, ObservabilityWindow } from "../types/observability";

const client = createObservabilityClient({ baseUrl: runtimeConfig.apiBaseUrl });

export function useObservability(window: ObservabilityWindow) {
  const [state, setState] = useState<ObservabilityState>("UNAVAILABLE");
  const [data, setData] = useState<ObservabilitySummary | null>(null);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    if (runtimeConfig.dataMode !== "api") return undefined;
    const controller = new AbortController();
    void client.getSummary(window, controller.signal).then((summary) => {
      setData(summary);
      setState(summary.state);
    }, (error: unknown) => {
      if (controller.signal.aborted) return;
      setData(null);
      setState(error instanceof ObservabilityApiError && error.status === 403 ? "NO_PERMISSION" : "UNAVAILABLE");
    });
    return () => controller.abort();
  }, [revision, window]);

  return { state, data, refresh };
}
