import { useEffect, useState, useSyncExternalStore } from "react";

import { getSessionSnapshot, isSessionActive, subscribeToSession } from "../auth/session";
import { runtimeConfig } from "../config/runtime";
import { TaskEventClient } from "../services/task-event-client";
import type { AgentRun, AgentStatus } from "../types/dispatch";
import type { TaskEvent } from "../types/task-events";

const nodes = ["intake", "entity_memory", "graph_memory", "environment", "capacity", "routing", "dispatch", "audit"];
const names: Record<string, string> = { intake: "接入智能体", entity_memory: "实体记忆智能体", graph_memory: "图记忆智能体", environment: "环境智能体", capacity: "运力智能体", routing: "路径智能体", dispatch: "调度智能体", audit: "审核智能体" };
const initialAgents: AgentRun[] = nodes.map((id) => ({ id, name: names[id], status: "WAITING", elapsed: "—", output: "等待真实事件" }));

function mapStatus(event: TaskEvent): AgentStatus {
  if (event.event_type.endsWith("_STARTED")) return "RUNNING";
  if (event.event_type === "ENVIRONMENT_FALLBACK" || event.event_type === "GRAPH_MEMORY_DEGRADED") return "FALLBACK";
  if (event.event_type.endsWith("_COMPLETED")) return "SUCCESS";
  if (event.event_type === "TASK_REVIEW_REQUIRED" || event.event_type === "TASK_FAILED") return "FAILED";
  return "WAITING";
}

export function useTaskEvents(taskId: string, onTerminal: () => void) {
  const session = useSyncExternalStore(subscribeToSession, getSessionSnapshot, getSessionSnapshot);
  const [connection, setConnection] = useState<"CONNECTED" | "RECONNECTING" | "DISCONNECTED">("DISCONNECTED");
  const [events, setEvents] = useState<TaskEvent[]>([]);
  useEffect(() => {
    if (runtimeConfig.dataMode !== "api" || session.status !== "authenticated" || !taskId.trim()) return undefined;
    const client = new TaskEventClient(runtimeConfig.apiBaseUrl, taskId, {
      onState: setConnection,
      onTerminal,
      onEvent: (event) => setEvents((current) => [...current, event]),
      isSessionActive,
    });
    client.connect();
    return () => client.close();
  }, [session.status, taskId, onTerminal]);
  const taskEvents = events.filter((event) => event.task_id === taskId);
  const agents = taskEvents.reduce<AgentRun[]>((current, event) => !nodes.includes(event.node) ? current : current.map((agent) => agent.id === event.node ? { ...agent, status: mapStatus(event), output: event.event_type, detail: Object.keys(event.data).length ? JSON.stringify(event.data) : undefined } : agent), initialAgents);
  return { agents, connection, events: taskEvents };
}
