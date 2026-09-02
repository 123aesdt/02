import { useCallback, useEffect, useState } from "react";

import { runtimeConfig } from "../config/runtime";
import { ApiError } from "../services/api/client";
import { workspaceReadClient } from "../services/api/workspace-read-client";
import type {
  AnomalyFilters,
  AnomalyListItem,
  OrderListItem,
  OrdersFilters,
  OverviewResponse,
  MyTaskFilters,
  MyTaskPageResponse,
  PageFilters,
  PageResponse,
  ReviewListItem,
  RuntimeThreadFilters,
  RuntimeThreadListItem,
  VectorMemoryPageResponse,
} from "../types/workspace-read-models";
import type { ReadState } from "../types/workspace";

export type WorkspaceReadHookState<T> = ReadState<T> & { refresh: () => void };

type RequestFactory<T> = (signal: AbortSignal) => Promise<T>;
type PrimitiveDependency = string | number | boolean | null | undefined;

function apiErrorState<T>(error: unknown): ReadState<T> {
  if (error instanceof ApiError && error.status === 403) return { state: "FORBIDDEN", data: null };
  if (error instanceof ApiError && error.status === 503) return { state: "UNAVAILABLE", data: null };
  return { state: "ERROR", data: null };
}

function withoutEmptyFilters<T extends Record<string, string | number | null | undefined>>(filters: T): T {
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== undefined && value !== null && value !== "")) as T;
}

function useWorkspaceRead<T>(
  request: RequestFactory<T>,
  dependencies: readonly PrimitiveDependency[],
  isEmpty: (data: T) => boolean = () => false,
): WorkspaceReadHookState<T> {
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [result, setResult] = useState<ReadState<T>>({ state: "LOADING", data: null });
  const refresh = useCallback(() => { setRefreshVersion((current) => current + 1); }, []);

  useEffect(() => {
    if (runtimeConfig.dataMode !== "api") {
      return undefined;
    }
    const controller = new AbortController();
    void Promise.resolve().then(() => {
      if (!controller.signal.aborted) setResult({ state: "LOADING", data: null });
    });
    void request(controller.signal).then((data) => {
      if (controller.signal.aborted) return;
      setResult(isEmpty(data) ? { state: "EMPTY", data: null } : { state: "READY", data });
    }, (error: unknown) => {
      if (controller.signal.aborted) return;
      setResult(apiErrorState(error));
    });
    return () => controller.abort();
  // The caller supplies only primitive dependencies, avoiding unstable filter object identity.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request, refreshVersion, ...dependencies]);

  const state = runtimeConfig.dataMode === "api" ? result : { state: "NOT_EXPOSED", data: null } as ReadState<T>;
  return { ...state, refresh } as WorkspaceReadHookState<T>;
}

function usePageRead<T>(request: RequestFactory<PageResponse<T>>, dependencies: readonly PrimitiveDependency[]) {
  return useWorkspaceRead(request, dependencies, (page) => page.items.length === 0);
}

export function useOverview(): WorkspaceReadHookState<OverviewResponse> {
  const request = useCallback((signal: AbortSignal) => workspaceReadClient.getOverview(signal), []);
  return useWorkspaceRead(request, []);
}

export function useOrdersRead(filters: OrdersFilters = {}): WorkspaceReadHookState<PageResponse<OrderListItem>> {
  const { limit, cursor, query, status } = filters;
  const request = useCallback(
    (signal: AbortSignal) => workspaceReadClient.getOrders(withoutEmptyFilters({ limit, cursor, query, status }), signal),
    [limit, cursor, query, status],
  );
  return usePageRead(request, [limit, cursor, query, status]);
}

export function useAnomaliesRead(filters: AnomalyFilters = {}): WorkspaceReadHookState<PageResponse<AnomalyListItem>> {
  const { limit, cursor, query, risk, status } = filters;
  const request = useCallback(
    (signal: AbortSignal) => workspaceReadClient.getAnomalies(withoutEmptyFilters({ limit, cursor, query, risk, status }), signal),
    [limit, cursor, query, risk, status],
  );
  return usePageRead(request, [limit, cursor, query, risk, status]);
}

export function useReviewsRead(filters: PageFilters = {}): WorkspaceReadHookState<PageResponse<ReviewListItem>> {
  const { limit, cursor } = filters;
  const request = useCallback(
    (signal: AbortSignal) => workspaceReadClient.getReviews(withoutEmptyFilters({ limit, cursor }), signal),
    [limit, cursor],
  );
  return usePageRead(request, [limit, cursor]);
}

export function useMyTasksRead(filters: MyTaskFilters = {}): WorkspaceReadHookState<MyTaskPageResponse> {
  const { limit, cursor, state } = filters;
  const request = useCallback(
    (signal: AbortSignal) => workspaceReadClient.getMyTasks(withoutEmptyFilters({ limit, cursor, state }), signal),
    [limit, cursor, state],
  );
  return useWorkspaceRead(request, [limit, cursor, state], (page) => page.items.length === 0 && page.summary.total === 0);
}

export function useRuntimeThreadsRead(filters: RuntimeThreadFilters = {}): WorkspaceReadHookState<PageResponse<RuntimeThreadListItem>> {
  const { limit, cursor, status } = filters;
  const request = useCallback(
    (signal: AbortSignal) => workspaceReadClient.getRuntimeThreads(withoutEmptyFilters({ limit, cursor, status }), signal),
    [limit, cursor, status],
  );
  return usePageRead(request, [limit, cursor, status]);
}

export function useVectorMemoriesRead(filters: PageFilters = {}): WorkspaceReadHookState<VectorMemoryPageResponse> {
  const { limit, cursor } = filters;
  const request = useCallback(
    (signal: AbortSignal) => workspaceReadClient.getVectorMemories(withoutEmptyFilters({ limit, cursor }), signal),
    [limit, cursor],
  );
  return useWorkspaceRead(request, [limit, cursor]);
}
