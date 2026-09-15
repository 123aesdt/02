export type DataMode = "mock" | "api";

type RuntimeEnvironment = {
  MODE?: string;
  VITE_DATA_MODE?: string;
  VITE_API_BASE_URL?: string;
  VITE_AUTHENTICATION_MODE?: string;
  VITE_RUNTIME_THREAD_STATE_ENABLED?: string;
  VITE_AMAP_KEY?: string;
  VITE_AMAP_SECURITY_CODE?: string;
};

export function resolveRuntimeConfig(environment: RuntimeEnvironment) {
  const development = environment.MODE === "development";
  const defaultMode: DataMode = development ? "api" : "mock";
  const amapKey = environment.VITE_AMAP_KEY?.trim() ?? "";
  const amapSecurityCode = environment.VITE_AMAP_SECURITY_CODE?.trim() ?? "";
  return {
    dataMode: environment.VITE_DATA_MODE === "api"
      ? "api"
      : environment.VITE_DATA_MODE === "mock"
        ? "mock"
        : defaultMode,
    apiBaseUrl: environment.VITE_API_BASE_URL ?? (development ? "http://localhost:8001" : "http://localhost:8000"),
    authenticationMode: environment.VITE_AUTHENTICATION_MODE === "oidc_jwt" ? "oidc_jwt" : "development_jwt" as "development_jwt" | "oidc_jwt",
    runtimeThreadStateEnabled: environment.VITE_RUNTIME_THREAD_STATE_ENABLED === "true"
      || (environment.VITE_RUNTIME_THREAD_STATE_ENABLED === undefined && development),
    amap: {
      enabled: Boolean(amapKey && amapSecurityCode),
      key: amapKey,
      securityCode: amapSecurityCode,
    },
  };
}

export const runtimeConfig = resolveRuntimeConfig(import.meta.env);
