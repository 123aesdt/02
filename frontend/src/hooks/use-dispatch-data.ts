import { useEffect, useState } from "react";

import { getDashboardSnapshot, getDispatchDetail } from "../services/dispatch-service";
import { runtimeConfig } from "../config/runtime";
import type { DashboardSnapshot, DispatchDetail } from "../types/dispatch";

export function useDashboardData() {
  const [data, setData] = useState<DashboardSnapshot | null>(null);
  useEffect(() => {
    if (runtimeConfig.dataMode !== "mock") return undefined;
    let active = true;
    void getDashboardSnapshot().then((snapshot) => { if (active) setData(snapshot); });
    return () => { active = false; };
  }, []);
  return data;
}

export function useDispatchData(taskId: string) {
  const [data, setData] = useState<DispatchDetail | null>(null);
  useEffect(() => { void getDispatchDetail(taskId).then(setData); }, [taskId]);
  return data;
}
