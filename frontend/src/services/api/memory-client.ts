import { runtimeConfig } from "../../config/runtime";
import type { SharedMemoryFactDetail } from "../../types/memory";
import { createApiClient, type ApiClient } from "./client";

const defaultClient = createApiClient({ baseUrl: runtimeConfig.apiBaseUrl });

export async function getMemoryFact(
  factKey: string,
  client: ApiClient = defaultClient,
): Promise<SharedMemoryFactDetail> {
  const response = await client.request<SharedMemoryFactDetail>(
    `/api/v1/memory/facts/${encodeURIComponent(factKey)}`,
  );
  return response.data;
}

