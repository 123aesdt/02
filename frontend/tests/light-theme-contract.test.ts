import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import entrySource from "../src/main.tsx?raw";

describe("V2-F2 semantic light theme", () => {
  it("test_light_theme_app_shell defines the exact white background and semantic tokens", () => {
    const tokenStyles = readFileSync(resolve("src/styles/tokens.css"), "utf8");

    expect(tokenStyles).toMatch(/--background:\s*#ffffff/i);
    expect(tokenStyles).toContain("color-scheme: light");

    for (const token of [
      "surface-primary",
      "surface-secondary",
      "surface-subtle",
      "surface-hover",
      "surface-selected",
      "border",
      "border-strong",
      "text-primary",
      "text-secondary",
      "text-tertiary",
      "brand",
      "brand-hover",
      "brand-subtle",
      "brand-border",
      "success",
      "warning",
      "danger",
      "info",
      "focus-ring",
      "overlay",
      "shadow-raised",
      "shadow-sm",
      "shadow-md",
      "radius-sm",
      "radius-md",
      "radius-lg",
      "radius-pill",
    ]) {
      expect(tokenStyles).toContain(`--${token}:`);
    }
  });

  it("loads tokens before application styles", () => {
    const tokenImport = entrySource.indexOf('import "./styles/tokens.css"');
    const applicationImport = entrySource.indexOf('import "./styles/index.css"');

    expect(tokenImport).toBeGreaterThanOrEqual(0);
    expect(tokenImport).toBeLessThan(applicationImport);
  });
});
