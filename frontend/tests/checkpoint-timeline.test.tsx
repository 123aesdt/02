import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it } from "vitest";

import { CheckpointTimeline } from "../src/components/checkpoint-timeline";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
afterEach(() => document.body.replaceChildren());

it("distinguishes agent checkpoints from runtime override state versions", async () => {
  const container = document.createElement("div"); document.body.append(container); const root = createRoot(container);
  await act(async () => { root.render(<CheckpointTimeline checkpoints={[
    { checkpoint_id: "checkpoint-7", state_version: 7, node: "environment", next_node: "capacity", created_at: "2026-08-27T00:00:01Z" },
  ]} overrides={[
    { override_id: "override-1", thread_id: "thread-1", task_id: "TASK-1", operator_id: "dispatcher-1", operator_role: "dispatcher", status: "APPLIED", decision: "ALLOWED", expected_version: 7, expected_next_node: "capacity", before_state_version: 7, after_state_version: 8, entity_type: "Vehicle", entity_id: "vehicle-001", field: "status", old_value: "NORMAL", new_value: "BROKEN", reason: "爆胎", source_checkpoint_id: "checkpoint-7", result_checkpoint_id: "checkpoint-8", event_status: "PUBLISHED", error_code: null, requested_at: "2026-08-27T00:00:01.500Z", started_at: null, completed_at: "2026-08-27T00:00:02Z", replayed: false },
  ]}/>); });

  expect(container.textContent).toContain("智能体检查点");
  expect(container.textContent).toContain("检查点 ID checkpoint-7");
  expect(container.textContent).toContain("检查点状态版本 7");
  expect(container.textContent).toContain("运行态干预");
  expect(container.textContent).toContain("运行态 V7 → V8");
  expect(container.textContent).toContain("checkpoint-7 → checkpoint-8");
});
