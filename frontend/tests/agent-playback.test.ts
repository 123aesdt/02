import { describe, expect, it } from "vitest";

import { getPlaybackStatus } from "../src/features/dispatch/agent-playback";

describe("Agent playback state", () => {
  it("keeps future agents waiting while the current agent is running", () => {
    expect(getPlaybackStatus(1, 0)).toBe("RUNNING");
    expect(getPlaybackStatus(1, 2)).toBe("WAITING");
  });

  it("ends the environment node in fallback and the audit node approved", () => {
    expect(getPlaybackStatus(5, 3)).toBe("FALLBACK");
    expect(getPlaybackStatus(9, 7)).toBe("APPROVED");
  });
});
