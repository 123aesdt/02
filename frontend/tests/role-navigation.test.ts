import { describe, expect, it } from "vitest";

import { permissionsForRole, type Permission, type Role } from "../src/auth/permissions";
import { flattenNavigationLabels, resolveNavigation } from "../src/navigation/navigation-resolver";

function labels(roles: Role[], permissions: readonly Permission[] = permissionsForRole(roles[0])) {
  return flattenNavigationLabels(resolveNavigation({ roles, permissions }));
}

describe("canonical permission-driven navigation", () => {
  it("delivery employees only see their own task entry", () => {
    expect(labels(["EMPLOYEE"])).toEqual(["我的任务", "提出问题"]);
  });

  it("test_dispatcher_navigation exposes business work without technical control planes", () => {
    expect(labels(["DISPATCHER"])).toEqual(["调度工作台", "异常中心", "智能调度", "运单管理"]);
  });

  it("test_dispatcher_no_monitor_navigation", () => {
    const resolved = labels(["DISPATCHER"]);
    expect(resolved).not.toContain("系统监控");
    expect(resolved).not.toContain("运行态");
    expect(resolved).not.toContain("记忆中心");
  });

  it("test_permission_driven_navigation treats server permissions as capability truth", () => {
    const resolved = labels(["DISPATCHER"], ["monitor:read"]);
    expect(resolved).toContain("系统监控");
    expect(resolved).not.toContain("智能调度");
  });

  it("test_multi_role_permissions keeps the server permission union", () => {
    const resolved = labels(["DISPATCHER", "OPERATOR"], ["dispatch:read", "dispatch:create", "monitor:read"]);
    expect(resolved[0]).toBe("运行中心");
    expect(resolved).toContain("智能调度");
    expect(resolved).toContain("系统监控");
    expect(resolved).not.toContain("运行态");
  });

  it("keeps the remaining role navigation distinct and legitimate", () => {
    expect(labels(["SUPERVISOR"])).toEqual(expect.arrayContaining(["调度主管台", "待复核", "运行态", "系统监控", "审计证据"]));
    expect(labels(["OPERATOR"])).toEqual(expect.arrayContaining(["运行中心", "智能体中心", "运行态", "系统监控", "运维审计"]));
    expect(labels(["AUDITOR"])).toEqual(expect.arrayContaining(["审计中心", "记忆中心", "运行态", "系统监控"]));
    expect(labels(["ADMIN"])).toEqual(expect.arrayContaining(["系统总览", "车辆态势地图", "异常中心", "智能调度", "运行中心", "审计中心"]));
    expect(labels(["SUPERVISOR"])).toContain("车辆态势地图");
    expect(labels(["EMPLOYEE"])).not.toContain("车辆态势地图");
    expect(labels(["ADMIN"])).not.toContain("用户管理");
  });
});
