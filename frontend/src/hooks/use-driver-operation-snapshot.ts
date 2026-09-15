import { useCallback, useEffect, useRef, useState } from "react";

import { vehicleOperationsClient } from "../services/api/vehicle-operations-client";
import type { VehicleOperationSnapshot } from "../types/vehicle-operations";

export function useDriverOperationSnapshot(taskId: string) {
  const [snapshot, setSnapshot] = useState<VehicleOperationSnapshot | null>(null);
  const [attemptedTaskId, setAttemptedTaskId] = useState("");
  const [connected, setConnected] = useState(false);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    if (!taskId) return;
    try {
      const next = await vehicleOperationsClient.getDriverOperationSnapshot(taskId);
      if (mounted.current) {
        setSnapshot(next);
        setConnected(true);
      }
    } catch {
      if (mounted.current) {
        setSnapshot(null);
        setConnected(false);
      }
    } finally {
      if (mounted.current) setAttemptedTaskId(taskId);
    }
  }, [taskId]);

  useEffect(() => {
    mounted.current = true;
    const initial = window.setTimeout(refresh, 0);
    const polling = window.setInterval(refresh, 3000);
    return () => {
      mounted.current = false;
      window.clearTimeout(initial);
      window.clearInterval(polling);
    };
  }, [refresh, taskId]);

  const visibleSnapshot = snapshot?.task_id === taskId ? snapshot : null;
  return {
    snapshot: visibleSnapshot,
    loading: Boolean(taskId) && attemptedTaskId !== taskId,
    connected: connected && Boolean(visibleSnapshot),
    refresh,
  };
}
