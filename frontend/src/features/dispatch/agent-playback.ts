import type { AgentStatus } from "../../types/dispatch";

export function getPlaybackStatus(step: number, agentIndex: number): AgentStatus {
  if (agentIndex >= step) return "WAITING";
  if (agentIndex === step - 1 && step <= 8) return "RUNNING";
  if (agentIndex === 3) return "FALLBACK";
  if (agentIndex === 7) return "APPROVED";
  return "SUCCESS";
}
