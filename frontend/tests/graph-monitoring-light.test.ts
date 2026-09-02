import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

function source(path: string) {
  return readFileSync(resolve(path), "utf8");
}

describe("graph and monitoring light surfaces", () => {
  it("test_graph_light_theme", () => {
    const styles = source("src/styles/light-migration.css");
    expect(styles).toMatch(/\.graph-canvas\s*\{[^}]*background:\s*var\(--surface-secondary\)/i);
    expect(styles).toMatch(/\.graph-node\s*\{[^}]*color:\s*var\(--text-primary\)[^}]*background:\s*var\(--surface-primary\)/i);
  });

  it("test_monitoring_light_theme", () => {
    const styles = source("src/styles/light-migration.css");
    expect(styles).toMatch(/\.live-observability-panel\s*\{[^}]*background:\s*var\(--surface-primary\)/i);
    expect(styles).toMatch(/\.live-metric-grid article\s*\{[^}]*background:\s*var\(--surface-secondary\)/i);
  });

  it("test_white_graph_inspector", () => {
    const styles = source("src/styles/light-migration.css");
    expect(styles).toMatch(/\.graph-property-inspector\s*\{[^}]*color:\s*var\(--text-primary\)[^}]*background:\s*var\(--surface-primary\)/i);
    expect(styles).toMatch(/\.graph-path-panel\s*\{[^}]*background:\s*var\(--surface-primary\)/i);
  });

  it("test_white_monitoring_chart", () => {
    const styles = source("src/styles/light-migration.css");
    expect(styles).toMatch(/\.observability-trend\s*\{[^}]*color:\s*var\(--brand\)/i);
    expect(styles).toMatch(/\.live-metric-grid strong\s*\{[^}]*color:\s*var\(--text-primary\)/i);
    expect(styles).toMatch(/\.monitor-state-message\s*\{[^}]*color:\s*var\(--warning\)[^}]*background:\s*var\(--warning-subtle\)/i);
    expect(source("src/components/observability-trend.tsx")).toContain('stroke="currentColor"');
    expect(source("src/components/live-observability-panel.tsx")).toContain("打开 Grafana");
  });

  it("exposes the selected graph node to keyboard and assistive technology", () => {
    const graphSource = source("src/components/graph-visualization.tsx");
    expect(graphSource).toContain("aria-pressed={selectedId === entity.id}");
    expect(graphSource).toContain('type="button"');
    expect(graphSource).toContain("onFocus={() => onSelect(entity)}");
  });
});
