import { describe, expect, it } from "vitest";

import { localizeRole, primaryRole } from "../src/auth/principal-view";
import { resolveRoleLanding } from "../src/navigation/role-landing-resolver";

describe("role landing resolver", () => {
  it("test_role_landing_resolver maps every canonical role to its approved workspace", () => {
    expect(resolveRoleLanding(["EMPLOYEE"])).toBe("/my-tasks");
    expect(resolveRoleLanding(["DISPATCHER"])).toBe("/workspace");
    expect(resolveRoleLanding(["SUPERVISOR"])).toBe("/supervisor");
    expect(resolveRoleLanding(["OPERATOR"])).toBe("/operations");
    expect(resolveRoleLanding(["AUDITOR"])).toBe("/audit");
    expect(resolveRoleLanding(["ADMIN"])).toBe("/overview");
  });

  it("uses the approved multi-role priority without adding permissions", () => {
    expect(primaryRole(["DISPATCHER", "AUDITOR", "SUPERVISOR"])).toBe("SUPERVISOR");
    expect(localizeRole("SUPERVISOR")).toBe("调度主管");
    expect(primaryRole(["UNKNOWN", "DISPATCHER"])).toBe("DISPATCHER");
    expect(resolveRoleLanding(["UNKNOWN"])).toBeNull();
  });
});
