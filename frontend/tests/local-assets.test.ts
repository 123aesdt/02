import { describe, expect, it } from "vitest";

import stylesheet from "../src/styles/index.css?raw";

describe("local runtime assets", () => {
  it("does not require a remote stylesheet to render the application", () => {
    expect(stylesheet).not.toMatch(/@import\s+url\(["']?https?:\/\//i);
  });
});
