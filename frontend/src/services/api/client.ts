import { expireSession, getSessionSnapshot } from "../../auth/session";

export interface ApiErrorBody {
  code?: string;
  message?: string;
  detail?: unknown;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiClient {
  request<T>(path: string, init?: RequestInit): Promise<{ data: T; status: number }>;
}

export interface ApiClientOptions {
  baseUrl: string;
  fetchImpl?: typeof fetch;
  getAccessToken?: () => string | null;
  onUnauthorized?: () => void;
}

function errorBody(body: unknown): ApiErrorBody {
  if (typeof body !== "object" || body === null) return {};
  const candidate = body as ApiErrorBody;
  if (typeof candidate.detail === "object" && candidate.detail !== null) {
    return { ...(candidate.detail as ApiErrorBody), detail: candidate.detail };
  }
  return candidate;
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  const { baseUrl, fetchImpl = fetch } = options;
  const normalizedBaseUrl = baseUrl.replace(/\/$/, "");
  return {
    async request<T>(path: string, init: RequestInit = {}) {
      const token = (options.getAccessToken ?? (() => getSessionSnapshot().accessToken))();
      const headers = new Headers(init.headers);
      if (!headers.has("Accept")) headers.set("Accept", "application/json");
      if (token && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);
      const response = await fetchImpl(`${normalizedBaseUrl}${path}`, {
        ...init,
        headers,
      });
      const raw = await response.text();
      const body: unknown = raw ? JSON.parse(raw) : null;
      if (!response.ok && response.status !== 202) {
        if (response.status === 401) (options.onUnauthorized ?? expireSession)();
        if (response.status === 422) {
          const error = errorBody(body);
          if (error.code) {
            throw new ApiError(422, error.code, error.message ?? "请求未通过业务校验。", error.detail);
          }
          throw new ApiError(422, "VALIDATION_ERROR", "提交信息不完整或格式不正确。", body);
        }
        const error = errorBody(body);
        throw new ApiError(response.status, error.code ?? "API_ERROR", error.message ?? "请求暂时无法完成。", error.detail ?? body);
      }
      return { data: body as T, status: response.status };
    },
  };
}
