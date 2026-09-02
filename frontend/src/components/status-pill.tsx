import type { AgentStatus } from "../types/dispatch";
import { localizeStatus } from "../utils/presentation-labels";

export function StatusPill({ status }: { status: AgentStatus | string }) {
  return <span className={`status-pill status-${status.toLowerCase()}`}>{localizeStatus(status)}</span>;
}
