import { useCallback, useEffect, useRef, useState } from "react";

import { vehicleOperationsClient } from "../services/api/vehicle-operations-client";
import type { VehicleOperationSnapshot } from "../types/vehicle-operations";


export function useVehicleOperationSnapshot(taskId: string, fallback: VehicleOperationSnapshot | null = null, enabled = true) {
  const [snapshot, setSnapshot] = useState<VehicleOperationSnapshot | null>(fallback);
  const [connection, setConnection] = useState<"CONNECTED" | "RECONNECTING">("RECONNECTING");
  const [loading, setLoading] = useState(enabled && fallback === null);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    if (!taskId || !enabled) return;
    if (mounted.current) setLoading(true);
    setError(null);
    try {
      const next = await vehicleOperationsClient.getMapSnapshot(taskId);
      if (mounted.current) {
        setSnapshot(next);
        setConnection("CONNECTED");
      }
    } catch {
      if (mounted.current) {
        setConnection("RECONNECTING");
        setError("当前调度尚未生成救援维修执行记录。");
      }
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [enabled, taskId]);

  useEffect(() => {
    mounted.current = true;
    if (!enabled) {
      return () => { mounted.current = false; };
    }
    const initialRefresh = window.setTimeout(refresh, 0);
    const timer = window.setInterval(refresh, 1000);
    return () => {
      mounted.current = false;
      window.clearTimeout(initialRefresh);
      window.clearInterval(timer);
    };
  }, [enabled, refresh]);

  return { snapshot, connection, loading, error, refresh };
}
