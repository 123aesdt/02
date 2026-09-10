import type { RoutePlanResponse, VehicleAllocationResponse } from "../../services/api/dispatch-adapter";

function hasVehicleFailureEvidence(allocation: VehicleAllocationResponse | null | undefined): boolean {
  if (!allocation) return false;
  if (allocation.vehicle_reassigned) return true;
  return allocation.candidate_vehicles.some((candidate) => (
    candidate.vehicle_id === allocation.original_vehicle_id
    && (candidate.vehicle_status === "BROKEN" || candidate.exclusion_reasons.includes("ORIGINAL_VEHICLE_EXCLUDED"))
  ));
}

export function resolveEvidenceScenario(
  anomalyType: string | null | undefined,
  vehicleAllocation: VehicleAllocationResponse | null | undefined,
  routePlan: RoutePlanResponse | null | undefined,
) {
  const normalizedType = anomalyType?.trim().toUpperCase() ?? null;
  return {
    vehicle: normalizedType ? normalizedType === "VEHICLE_BREAKDOWN" && Boolean(vehicleAllocation) : hasVehicleFailureEvidence(vehicleAllocation),
    route: normalizedType ? normalizedType === "ROAD_BLOCKED" && Boolean(routePlan) : Boolean(routePlan?.blocked_edge_ids.length),
  };
}
