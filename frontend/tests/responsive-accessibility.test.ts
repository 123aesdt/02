import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const styles = readFileSync(resolve("src/styles/light-migration.css"), "utf8");
const statusBadge = readFileSync(resolve("src/components/ui/status-badge.tsx"), "utf8");
const runtimeDialog = readFileSync(resolve("src/components/runtime-override-dialog.tsx"), "utf8");
const memoryPage = readFileSync(resolve("src/pages/memory-page.tsx"), "utf8");

describe("responsive and accessibility contracts", () => {
  it("keeps core content bounded at 1366 and fluid at wide viewports", () => {
    expect(styles).toMatch(/@media\s*\(max-width:\s*1366px\)/i);
    expect(styles).toMatch(/\.table-wrap[^{]*\{[^}]*overflow(?:-x)?:\s*auto/i);
    expect(styles).toMatch(/body,[\s\S]*#root\s*\{[^}]*min-width:\s*0/i);
    expect(styles).not.toMatch(/max-width:\s*(?:1100|1200|1280)px[^}]*\.page-content/i);
  });

  it("provides keyboard focus, tabs and a trapped danger dialog", () => {
    expect(styles).toMatch(/:focus-visible[\s\S]*outline:\s*2px solid var\(--focus-ring\)/i);
    expect(memoryPage).toContain('role="tablist"');
    expect(memoryPage).toContain('aria-selected={tab === id}');
    expect(runtimeDialog).toContain('role="dialog"');
    expect(runtimeDialog).toContain('event.key !== "Tab"');
    expect(runtimeDialog).toContain('event.key === "Escape"');
  });

  it("does not communicate status by color alone", () => {
    expect(statusBadge).toContain("ui-status-badge__marker");
    expect(statusBadge).toContain("aria-label=");
    expect(statusBadge).toContain("presentation.label");
  });

  it("supports reduced motion", () => {
    expect(styles).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/i);
    expect(styles).toMatch(/animation-duration:\s*0\.01ms/i);
  });
});
