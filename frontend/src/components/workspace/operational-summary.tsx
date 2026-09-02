import { StatusBadge } from "../ui/status-badge";
import type { WorkspaceMetric } from "../../types/workspace";

export function OperationalSummary({ title, metrics }: { title: string; metrics: readonly WorkspaceMetric[] }) {
  return <section className="operational-summary" aria-labelledby="operational-summary-title">
    <h2 id="operational-summary-title">{title}</h2>
    <div className="operational-summary__items">
      {metrics.map((metric) => <article key={metric.id}>
        <span>{metric.label}</span>
        {metric.value === null
          ? <StatusBadge status="NOT_EXPOSED" />
          : <strong>{metric.value}</strong>}
      </article>)}
    </div>
  </section>;
}
