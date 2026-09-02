import { describe, expect, it } from "vitest";

import { resolveRuntimeConfig } from "../src/config/runtime";

describe("runtime configuration", () => {
  it("uses the real Docker API for an unconfigured Vite development server", () => {
    expect(resolveRuntimeConfig({ MODE: "development" })).toMatchObject({
      dataMode: "api",
      apiBaseUrl: "http://localhost:8001",
      authenticationMode: "development_jwt",
      runtimeThreadStateEnabled: true,
    });
  });

  it("keeps tests on explicit mock mode and honors configured API endpoints", () => {
    expect(resolveRuntimeConfig({ MODE: "test" }).dataMode).toBe("mock");
    expect(resolveRuntimeConfig({
      MODE: "production",
      VITE_DATA_MODE: "api",
      VITE_API_BASE_URL: "https://countyflow.example",
      VITE_AUTHENTICATION_MODE: "oidc_jwt",
      VITE_RUNTIME_THREAD_STATE_ENABLED: "true",
    })).toEqual({
      dataMode: "api",
      apiBaseUrl: "https://countyflow.example",
      authenticationMode: "oidc_jwt",
      runtimeThreadStateEnabled: true,
    });
  });
});
