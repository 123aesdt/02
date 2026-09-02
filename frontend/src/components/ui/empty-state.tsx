import { CircleOff, Inbox, LockKeyhole, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

export type EmptyStateKind = "empty" | "not-exposed" | "forbidden" | "unavailable" | "error";

export interface EmptyStateProps {
  kind: EmptyStateKind;
  title: string;
  description?: string;
  action?: ReactNode;
}

const ICONS = {
  empty: Inbox,
  "not-exposed": CircleOff,
  forbidden: LockKeyhole,
  unavailable: TriangleAlert,
  error: TriangleAlert,
} as const;

export function EmptyState({ kind, title, description, action }: EmptyStateProps) {
  const Icon = ICONS[kind];
  return <div className="ui-empty-state" data-state={kind} role={kind === "error" ? "alert" : "status"}>
    <Icon size={22} aria-hidden="true" />
    <div>
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
    </div>
    {action ? <div className="ui-empty-state__action">{action}</div> : null}
  </div>;
}
