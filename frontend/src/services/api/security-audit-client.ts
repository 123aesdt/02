import { createApiClient } from "./client";

export type SecurityAuditStatus = "ALLOWED" | "DENIED" | "ERROR";

export interface SecurityAuditEvent {
  event_id: string;
  event_type: string;
  subject_id: string | null;
  permission: string | null;
  route_template: string;
  status: SecurityAuditStatus;
  reason_code: string;
  request_id: string;
  remote_ip: string | null;
  created_at: string;
}

interface SecurityAuditResponse {
  items: SecurityAuditEvent[];
}

interface Options {
  baseUrl: string;
  fetchImpl?: typeof fetch;
}

export class SecurityAuditApiError extends Error {
  constructor(public readonly status: number) {
    super(status === 403 ? "Audit permission is required" : "Security audit unavailable");
    this.name = "SecurityAuditApiError";
  }
}

export function createSecurityAuditClient({ baseUrl, fetchImpl = fetch }: Options) {
  const client = createApiClient({ baseUrl, fetchImpl });
  return {
    async listRecent(signal?: AbortSignal): Promise<SecurityAuditEvent[]> {
      try {
        const response = await client.request<SecurityAuditResponse>("/api/v1/security/audit?limit=100", { signal });
        return response.data.items;
      } catch (error) {
        const status = typeof error === "object" && error !== null && "status" in error ? Number(error.status) : 0;
        throw new SecurityAuditApiError(status);
      }
    },
  };
}
