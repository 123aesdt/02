import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";

import { RuntimeOverrideDialog } from "../src/components/runtime-override-dialog";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => {
  document.body.replaceChildren();
});

it("test_white_dialog_theme keeps the final intervention action in the Danger style", async () => {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<RuntimeOverrideDialog
      snapshot={{ threadId: "thread-1", taskId: "TASK-1", entityType: "Vehicle", entityId: "vehicle-1", field: "status", oldValue: "NORMAL", newValue: "BROKEN", expectedVersion: 7, expectedNextNode: "capacity", checkpointId: "checkpoint-7" }}
      context={null}
      reason="车辆已确认爆胎"
      stale={false}
      submission="IDLE"
      setReason={vi.fn()}
      onCancel={vi.fn()}
      onConfirm={vi.fn()}
    />);
  });

  const dialog = container.querySelector('[role="dialog"]');
  const confirm = [...container.querySelectorAll("button")].find((button) => button.textContent === "确认干预");
  expect(dialog?.getAttribute("data-surface")).toBe("dialog");
  expect(confirm?.classList.contains("button-danger")).toBe(true);
  expect(confirm?.classList.contains("button-primary")).toBe(false);
});
