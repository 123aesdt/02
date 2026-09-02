import type { OverrideDialogSnapshot, RuntimeInterventionContext, VehicleRuntimeStatus } from "../../types/runtime-override";

const targetValues = new Set<VehicleRuntimeStatus>(["BROKEN", "UNAVAILABLE", "MAINTENANCE"]);

export function createOverrideDialogSnapshot(
  context: RuntimeInterventionContext,
  newValue: VehicleRuntimeStatus,
): OverrideDialogSnapshot | null {
  const target = context.target;
  if (
    context.eligibility !== "ELIGIBLE" || !context.can_override || !context.canonical_checkpoint_id ||
    context.next_node !== "capacity" || target?.entity_type !== "Vehicle" || target.field !== "status" ||
    target.current_value !== "NORMAL" || !targetValues.has(newValue) || !target.allowed_new_values.includes(newValue)
  ) return null;
  return Object.freeze({
    threadId: context.thread_id,
    taskId: context.task_id,
    checkpointId: context.canonical_checkpoint_id,
    expectedVersion: context.state_version,
    expectedNextNode: "capacity",
    entityType: "Vehicle",
    entityId: target.entity_id,
    field: "status",
    oldValue: "NORMAL",
    newValue: newValue as Exclude<VehicleRuntimeStatus, "NORMAL">,
  });
}

export function isOverrideSnapshotStale(
  snapshot: OverrideDialogSnapshot,
  context: RuntimeInterventionContext | null,
): boolean {
  return !context || context.eligibility !== "ELIGIBLE" || context.state_version !== snapshot.expectedVersion ||
    context.canonical_checkpoint_id !== snapshot.checkpointId || context.next_node !== snapshot.expectedNextNode ||
    context.target?.entity_id !== snapshot.entityId || context.target.current_value !== snapshot.oldValue;
}
