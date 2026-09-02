import type { ProjectionStatus as ProjectionStatusValue } from "../types/memory";
import { localizeStatus } from "../utils/presentation-labels";

export function ProjectionStatus({ status }: { status: ProjectionStatusValue | string }) {
  const notActive = status === "STAGED" || status === "FINALIZING" || status === "PENDING";
  return <span className={`projection-status projection-${status.toLowerCase()}`}>投影{localizeStatus(status)}{notActive ? " · 未生效" : ""}</span>;
}
