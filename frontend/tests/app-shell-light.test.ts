import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const styles = readFileSync(resolve("src/styles/index.css"), "utf8");
const shellSource = readFileSync(resolve("src/components/app-shell.tsx"), "utf8");

describe("white enterprise App Shell", () => {
  it("test_light_theme_app_shell uses the exact semantic white surface", () => {
    expect(styles).toMatch(/body\s*\{[^}]*background:\s*var\(--background\)/i);
    expect(styles).toMatch(/\.app-shell\s*\{[^}]*background:\s*var\(--background\)/i);
    expect(styles).toMatch(/\.main-area\s*\{[^}]*background:\s*var\(--background\)/i);
    expect(styles).toMatch(/\.page-content\s*\{[^}]*background:\s*var\(--background\)/i);
  });

  it("test_light_theme_sidebar and topbar use light surface tokens", () => {
    expect(styles).toMatch(/\.sidebar\s*\{[^}]*border-right:\s*1px solid var\(--border\)[^}]*background:\s*var\(--surface-primary\)/i);
    expect(styles).toMatch(/\.topbar\s*\{[^}]*border-bottom:\s*1px solid var\(--border\)[^}]*background:\s*var\(--surface-primary\)/i);
    expect(shellSource).toContain('data-surface="sidebar"');
    expect(shellSource).toContain('data-surface="topbar"');
  });

  it("does not make an unverified worker-count claim", () => {
    expect(shellSource).not.toContain("3 个工作节点在线");
    expect(shellSource).not.toContain("系统运行正常");
  });
});
