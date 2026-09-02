import { useEffect, useMemo, useRef, useState } from "react";

import { useHasPermission } from "../auth/auth-state";
import type { DataMode } from "../config/runtime";
import { useRuntimeOverride } from "../hooks/use-runtime-override";
import { useRuntimeOverrideHistory } from "../hooks/use-runtime-override-history";
import { useRuntimeThread } from "../hooks/use-runtime-thread";
import { runtimeOverrideClient, type RuntimeOverrideClient } from "../services/api/runtime-override-client";
import { runtimeThreadClient, type RuntimeThreadClient } from "../services/api/runtime-thread-client";
import type { TaskEvent } from "../types/task-events";
import type { RuntimeOverrideHistory } from "../types/runtime-override";
import { CapacityEvidencePanel } from "./capacity-evidence-panel";
import { MockRuntimeInterventionWorkbench } from "./mock-runtime-intervention-workbench";
import { RuntimeEventTimeline } from "./runtime-event-timeline";
import { RuntimeInterventionPanel } from "./runtime-intervention-panel";
import { RuntimeOverrideHistoryPanel } from "./runtime-override-history";
import { RuntimeThreadPanel } from "./runtime-thread-panel";
import { CheckpointTimeline } from "./checkpoint-timeline";

const refreshEvents = new Set(["THREAD_CHECKPOINTED", "THREAD_RESUMED", "THREAD_TERMINAL", "RUNTIME_OVERRIDE_REQUESTED", "RUNTIME_OVERRIDE_APPLIED", "RUNTIME_OVERRIDE_REJECTED", "RUNTIME_OVERRIDE_CONFLICT", "RUNTIME_OVERRIDE_PARTIAL"]);

export function RuntimeWorkbench({ taskId, enabled, mode, events, threadClient = runtimeThreadClient, overrideClient = runtimeOverrideClient, onRuntimeRefresh, onHistoryChange }: {
  taskId: string; enabled: boolean; mode: DataMode; events: TaskEvent[]; threadClient?: RuntimeThreadClient; overrideClient?: RuntimeOverrideClient; onRuntimeRefresh?: () => void; onHistoryChange?: (history: RuntimeOverrideHistory | null) => void;
}) {
  const canReadRuntime = useHasPermission("runtime:read");
  const canOverrideRuntime = useHasPermission("runtime:override");
  const [threadRefresh, setThreadRefresh] = useState(0);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const permissionEnabled = enabled && canReadRuntime;
  const threadState = useRuntimeThread(taskId, permissionEnabled && mode === "api", threadClient, threadRefresh);
  const threadId = threadState.kind === "ready" ? threadState.detail.thread_id : null;
  const override = useRuntimeOverride(threadId, permissionEnabled && mode === "api", overrideClient, () => {
    setThreadRefresh((value) => value + 1); setHistoryRefresh((value) => value + 1); onRuntimeRefresh?.();
  });
  const history = useRuntimeOverrideHistory(threadId, permissionEnabled && mode === "api", overrideClient, historyRefresh);
  const relevantKey = useMemo(() => [...new Set(events.filter((item) => refreshEvents.has(item.event_type)).map((item) => item.event_id))].join("|"), [events]);
  const observed = useRef("");
  const queued = useRef(false);
  useEffect(() => { onHistoryChange?.(history); }, [history, onHistoryChange]);
  useEffect(() => {
    if (!relevantKey || relevantKey === observed.current || queued.current) return;
    observed.current = relevantKey; queued.current = true;
    let disposed = false;
    queueMicrotask(() => {
      if (disposed) return;
      queued.current = false; override.refresh(); setThreadRefresh((value) => value + 1); setHistoryRefresh((value) => value + 1); onRuntimeRefresh?.();
    });
    return () => { disposed = true; };
  }, [onRuntimeRefresh, override, relevantKey]);

  if (!enabled) return null;
  if (mode === "mock") return <MockRuntimeInterventionWorkbench />;
  if (!canReadRuntime) return <section className="authorization-state compact"><h2>运行态不可用</h2><p>当前身份缺少 runtime:read 权限。</p></section>;
  return <div className="runtime-workbench"><RuntimeThreadPanel taskId={taskId} enabled state={threadState} />
    {threadId ? <><CheckpointTimeline checkpoints={threadState.kind === "ready" ? threadState.history.items : []} overrides={history?.items ?? []}/><RuntimeInterventionPanel override={override} canOverride={canOverrideRuntime}/><RuntimeOverrideHistoryPanel history={history}/><CapacityEvidencePanel events={events}/><RuntimeEventTimeline events={events}/></> : null}
  </div>;
}
