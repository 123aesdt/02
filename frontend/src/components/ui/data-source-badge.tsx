import { Cloud, Database, HardDrive, Layers3 } from "lucide-react";

export type DataSourceProvenance = "LIVE" | "DEMO" | "MIXED" | "FALLBACK";

const presentations = {
  LIVE: { label: "实时业务数据", Icon: Cloud },
  DEMO: { label: "演示业务数据", Icon: Database },
  MIXED: { label: "混合业务数据", Icon: Layers3 },
  FALLBACK: { label: "本地保障数据", Icon: HardDrive },
} as const;

export function DataSourceBadge({ provenance, detail }: { provenance: DataSourceProvenance; detail?: string }) {
  const { label, Icon } = presentations[provenance];
  return <span className="data-source-badge" data-provenance={provenance} title={detail}>
    <Icon size={14}/><span><strong>{label}</strong>{detail ? <small>{detail}</small> : null}</span>
  </span>;
}
