export interface SkeletonProps {
  label: string;
  lines?: number;
}

export function Skeleton({ label, lines = 3 }: SkeletonProps) {
  return <div className="ui-skeleton" role="status" aria-label={label} aria-busy="true">
    <span className="sr-only">{label}</span>
    {Array.from({ length: Math.max(1, lines) }, (_, index) => (
      <span className="ui-skeleton__line" aria-hidden="true" key={index} />
    ))}
  </div>;
}
