import { useEffect, useState } from "react";
import { runtimeConfig } from "../config/runtime";
import { getAnomalies, getMemoryRecords, getOrders } from "../services/workspace-service";
import { getMemoryFact } from "../services/api/memory-client";
import type { AnomalyRecord, MemoryRecord, OrderRecord, Risk } from "../mocks/workspace-data";
import type { SharedMemoryFactDetail } from "../types/memory";

export function useAnomalies(filters: { query?: string; risk?: Risk | ""; type?: string; status?: string }) { const [data, setData] = useState<AnomalyRecord[]>([]); const { query, risk, type, status } = filters; useEffect(() => { if (runtimeConfig.dataMode !== "mock") return undefined; let active = true; void getAnomalies({ query, risk, type, status }).then((rows) => { if (active) setData(rows); }); return () => { active = false; }; }, [query, risk, type, status]); return data; }
export function useOrders(filters: { query?: string; status?: string }) { const [data, setData] = useState<OrderRecord[]>([]); const { query, status } = filters; useEffect(() => { if (runtimeConfig.dataMode !== "mock") return undefined; let active = true; void getOrders({ query, status }).then((rows) => { if (active) setData(rows); }); return () => { active = false; }; }, [query, status]); return data; }
export function useMemories(query: string) { const [data, setData] = useState<MemoryRecord[]>([]); useEffect(() => { if (runtimeConfig.dataMode !== "mock") return undefined; let active = true; void getMemoryRecords({ query }).then((rows) => { if (active) setData(rows); }); return () => { active = false; }; }, [query]); return data; }

export function useMemoryControlPlane(factKey: string) {
  const normalizedFactKey = factKey.trim();
  const enabled = runtimeConfig.dataMode === "api" && Boolean(normalizedFactKey);
  const [result, setResult] = useState<{
    factKey: string;
    data: SharedMemoryFactDetail | null;
    error: string | null;
  }>({ factKey: "", data: null, error: null });

  useEffect(() => {
    let active = true;
    if (!enabled) return () => { active = false; };
    void getMemoryFact(normalizedFactKey)
      .then((fact) => {
        if (active) setResult({ factKey: normalizedFactKey, data: fact, error: null });
      })
      .catch(() => {
        if (active) setResult({ factKey: normalizedFactKey, data: null, error: "控制面事实暂时不可用" });
      });
    return () => { active = false; };
  }, [enabled, normalizedFactKey]);

  const current = enabled && result.factKey === normalizedFactKey;
  return {
    data: current ? result.data : null,
    error: current ? result.error : null,
    loading: enabled && !current,
  };
}
