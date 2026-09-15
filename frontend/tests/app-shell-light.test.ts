import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const styles = readFileSync(resolve("src/styles/countyflow-night.css"), "utf8");
const shellSource = readFileSync(resolve("src/components/app-shell.tsx"), "utf8");

describe("CountyFlow night operations App Shell", () => {
  it("uses the selected deep-blue command-center surfaces", () => {
    expect(styles).toMatch(/--background:\s*#020b1c/i);
    expect(styles).toMatch(/\.app-shell\s*\{[^}]*background:\s*var\(--background\)/i);
    expect(styles).toMatch(/\.sidebar\s*\{[^}]*background:\s*#031329/i);
    expect(styles).toMatch(/\.topbar\s*\{[^}]*background:\s*rgba\(2,\s*12,\s*30,/i);
    expect(styles).toMatch(/\.page-content\s*\{[^}]*background:\s*transparent/i);
  });

  it("renders a route-aware logistics hero below the compact topbar", () => {
    expect(shellSource).toContain('data-surface="sidebar"');
    expect(shellSource).toContain('data-surface="topbar"');
    expect(shellSource).toContain('data-surface="page-hero"');
    expect(shellSource).toContain("pagePresentations");
    expect(shellSource).toContain("presentation.subtitle");
    expect(shellSource).toContain("presentation.tags.map");
  });

  it("does not make an unverified worker-count claim", () => {
    expect(shellSource).not.toContain("3 个工作节点在线");
    expect(shellSource).not.toContain("系统运行正常");
  });
});
