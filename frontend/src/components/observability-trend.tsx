export function ObservabilityTrend({ value }: { value: number | null | undefined }) {
  const normalized = typeof value === "number" ? Math.max(2, Math.min(22, value * 2 + 2)) : 2;
  return <svg className="observability-trend" viewBox="0 0 80 24" aria-hidden="true">
    <polyline points={`0,22 20,18 40,20 60,${24 - normalized} 80,${22 - normalized / 3}`} fill="none" stroke="currentColor" strokeWidth="2" />
  </svg>;
}
