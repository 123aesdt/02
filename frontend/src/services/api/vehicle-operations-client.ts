import { runtimeConfig } from "../../config/runtime";
import type { VehicleOperationSnapshot } from "../../types/vehicle-operations";
import { createApiClient, type ApiClientOptions } from "./client";


export function createVehicleOperationsClient(options: ApiClientOptions) {
  const client = createApiClient(options);
  return {
    async getMapSnapshot(taskId: string): Promise<VehicleOperationSnapshot> {
      const response = await client.request<VehicleOperationSnapshot>(
        `/api/v1/map/snapshot?task_id=${encodeURIComponent(taskId)}`,
      );
      return response.data;
    },
    async getDriverOperationSnapshot(taskId: string): Promise<VehicleOperationSnapshot> {
      const response = await client.request<VehicleOperationSnapshot>(
        "/api/v1/driver/operation-snapshot?task_id=" + encodeURIComponent(taskId),
      );
      return response.data;
    },
  };
}

export const vehicleOperationsClient = createVehicleOperationsClient({ baseUrl: runtimeConfig.apiBaseUrl });
