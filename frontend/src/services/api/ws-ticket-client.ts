import { runtimeConfig } from "../../config/runtime";
import { createApiClient } from "./client";

interface WsTicketResponse {
  ticket: string;
  target_type: "task";
  target_id: string;
  expires_at: string;
  expires_in_seconds: number;
}

const client = createApiClient({ baseUrl: runtimeConfig.apiBaseUrl });

export async function issueTaskWsTicket(taskId: string): Promise<string> {
  const response = await client.request<WsTicketResponse>("/api/v1/ws-tickets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_type: "task", target_id: taskId }),
  });
  return response.data.ticket;
}
