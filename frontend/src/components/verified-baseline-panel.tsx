import { verifiedV2Metrics } from "../mocks/v2-product-data";
import type { VerifiedMetric } from "../types/v2-product";

export function VerifiedBaselinePanel({ groups }: { groups?: VerifiedMetric["group"][] }) {
  const metrics = groups ? verifiedV2Metrics.filter((item) => groups.includes(item.group)) : verifiedV2Metrics;
  return <section className="workspace-panel verified-baseline-panel"><div className="panel-heading"><div><p className="eyebrow">V2-E 验收证据</p><h2>验收基线</h2></div><span className="source-label verified">已通过验收</span></div><p className="baseline-disclaimer">来自现有 V2-E 验收证据，非实时监控。</p><div className="baseline-grid">{metrics.map((metric) => <article key={metric.label}><span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.detail}</small></article>)}</div></section>;
}
