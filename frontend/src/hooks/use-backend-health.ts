import { useEffect, useState } from "react";

import { runtimeConfig } from "../config/runtime";
import { getBackendHealth } from "../services/dispatch-service";

export function useBackendHealth() {
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (runtimeConfig.dataMode !== "api") return undefined;
    const controller = new AbortController();
    void getBackendHealth(controller.signal).then(
      () => setConnected(true),
      () => setConnected(false),
    );
    return () => controller.abort();
  }, []);

  return connected;
}
