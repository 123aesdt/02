import { useCallback, useEffect, useMemo, useState } from "react";

import { isOverrideSnapshotStale, createOverrideDialogSnapshot } from "../features/runtime-override/dialog-snapshot";
import { runtimeOverrideError } from "../features/runtime-override/error-copy";
import { runtimeOverrideClient, type RuntimeOverrideClient } from "../services/api/runtime-override-client";
import type {
  OverrideDialogSnapshot,
  OverrideSubmissionState,
  RuntimeInterventionContext,
  RuntimeOverrideResponse,
  VehicleRuntimeStatus,
} from "../types/runtime-override";

function stateFor(result: RuntimeOverrideResponse): OverrideSubmissionState {
  if (result.status === "APPLIED") return "APPLIED";
  if (result.status === "PARTIAL") return "PARTIAL";
  if (result.status === "CONFLICT") return "CONFLICT";
  if (result.status === "REJECTED") return "REJECTED";
  return "FAILED";
}

export function useRuntimeOverride(
  threadId: string | null,
  enabled: boolean,
  client: RuntimeOverrideClient = runtimeOverrideClient,
  onBusinessChange?: () => void,
) {
  const [revision, setRevision] = useState(0);
  const [contextValue, setContextValue] = useState<{ key: string; context: RuntimeInterventionContext } | null>(null);
  const [unavailableKey, setUnavailableKey] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<OverrideDialogSnapshot | null>(null);
  const [reason, setReason] = useState("");
  const [attemptKey, setAttemptKey] = useState<string | null>(null);
  const [submission, setSubmission] = useState<OverrideSubmissionState>("IDLE");
  const [message, setMessage] = useState<string | null>(null);
  const [result, setResult] = useState<RuntimeOverrideResponse | null>(null);
  const requestKey = `${threadId}:${revision}`;
  const context = contextValue?.key === requestKey ? contextValue.context : null;
  const unavailable = unavailableKey === requestKey;

  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    if (!enabled || !threadId) return;
    const controller = new AbortController();
    void client.getInterventionContext(threadId, controller.signal).then((next) => {
      if (!controller.signal.aborted) setContextValue({ key: requestKey, context: next });
    }).catch(() => {
      if (!controller.signal.aborted) setUnavailableKey(requestKey);
    });
    return () => controller.abort();
  }, [client, enabled, requestKey, threadId]);

  const stale = useMemo(() => snapshot ? isOverrideSnapshotStale(snapshot, context) : false, [context, snapshot]);

  const open = useCallback((newValue: VehicleRuntimeStatus) => {
    if (!context) return;
    const next = createOverrideDialogSnapshot(context, newValue);
    if (!next) return;
    setSnapshot(next); setReason(""); setAttemptKey(null); setSubmission("IDLE"); setMessage(null); setResult(null);
  }, [context]);

  const close = useCallback(() => {
    setSnapshot(null); setReason(""); setAttemptKey(null); setSubmission("IDLE"); setMessage(null);
  }, []);

  const submit = useCallback(async () => {
    if (!snapshot || stale || reason.trim().length < 4 || submission === "SUBMITTING") return;
    const key = attemptKey ?? `runtime-override:${crypto.randomUUID()}`;
    if (!attemptKey) setAttemptKey(key);
    setSubmission("SUBMITTING"); setMessage(null);
    try {
      const next = await client.create(snapshot.threadId, {
        idempotency_key: key,
        entity_type: snapshot.entityType,
        entity_id: snapshot.entityId,
        field: snapshot.field,
        old_value: snapshot.oldValue,
        new_value: snapshot.newValue,
        reason: reason.trim(),
        expected_version: snapshot.expectedVersion,
        expected_next_node: snapshot.expectedNextNode,
      });
      setResult(next);
      const nextState = stateFor(next);
      setSubmission(nextState);
      setMessage(nextState === "APPLIED" ? "APPLIED：运行时状态已安全更新" : nextState === "PARTIAL" ? "状态修改正在恢复，请勿重复提交新的干预" : next.error_code);
      if (nextState === "APPLIED") setSnapshot(null);
      refresh(); onBusinessChange?.();
    } catch (error) {
      const mapped = runtimeOverrideError(error);
      setSubmission(mapped.state); setMessage(mapped.message);
    }
  }, [attemptKey, client, onBusinessChange, reason, refresh, snapshot, stale, submission]);

  useEffect(() => {
    if (submission !== "PARTIAL" || !result?.override_id) return;
    let disposed = false;
    const timers: number[] = [];
    [2000, 6000, 14000].forEach((delay) => {
      timers.push(window.setTimeout(() => {
        if (disposed) return;
        void client.get(result.override_id).then((next) => {
          if (disposed || next.status === "PARTIAL") return;
          setResult(next); setSubmission(stateFor(next));
          setMessage(next.status === "APPLIED" ? "APPLIED：运行时状态已安全更新" : next.error_code);
          if (next.status === "APPLIED") setSnapshot(null);
          refresh(); onBusinessChange?.();
        }).catch(() => undefined);
      }, delay));
    });
    return () => { disposed = true; timers.forEach((timer) => window.clearTimeout(timer)); };
  }, [client, onBusinessChange, refresh, result?.override_id, submission]);

  return { context, unavailable, loading: enabled && !context && !unavailable, snapshot, reason, setReason, stale, submission, message, result, open, close, submit, refresh, revision };
}
