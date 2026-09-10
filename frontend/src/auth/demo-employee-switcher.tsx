import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { runtimeConfig } from "../config/runtime";
import { FIXED_DEMO_EMPLOYEES, type DemoEmployee } from "./demo-employees";
import { useAuth } from "./auth-state";
import { localizeRole } from "./principal-view";

const FIXED_DEMO_EMPLOYEE_IDS = new Set(FIXED_DEMO_EMPLOYEES.map((employee) => employee.employee_id));

export function DemoEmployeeSwitcher({
  enabled,
  employees,
  currentEmployeeId,
  pending = false,
  onSelect,
}: {
  enabled: boolean;
  employees: readonly DemoEmployee[];
  currentEmployeeId: string | null;
  pending?: boolean;
  onSelect: (employeeId: string) => Promise<void> | void;
}) {
  if (!enabled) return null;
  const selectableEmployees = [
    ...FIXED_DEMO_EMPLOYEES,
    ...employees.filter((employee) => !FIXED_DEMO_EMPLOYEE_IDS.has(employee.employee_id)),
  ];
  return <label className="demo-employee-switcher">
    <span>演示身份</span>
    <select
      aria-label="切换演示员工"
      value={currentEmployeeId ?? ""}
      disabled={pending}
      onChange={(event) => {
        if (event.target.value) void onSelect(event.target.value);
      }}
    >
      <option value="">选择演示员工</option>
      {selectableEmployees.map((employee) => <option key={employee.employee_id} value={employee.employee_id}>
        {employee.display_name} · {localizeRole(employee.role)}
      </option>)}
    </select>
  </label>;
}

export function ConnectedDemoEmployeeSwitcher() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [switching, setSwitching] = useState(false);
  const enabled = runtimeConfig.dataMode === "api"
    && runtimeConfig.authenticationMode === "development_jwt";
  const currentEmployeeId = auth.principal?.subject_id.startsWith("CF-DEMO-")
    ? auth.principal.subject_id
    : null;

  return <DemoEmployeeSwitcher
    enabled={enabled}
    employees={auth.demoEmployees}
    currentEmployeeId={currentEmployeeId}
    pending={auth.demoEmployeesLoading || switching}
    onSelect={async (employeeId) => {
      setSwitching(true);
      try {
        await auth.switchDemoEmployee(employeeId);
        navigate("/", { replace: true });
      } finally {
        setSwitching(false);
      }
    }}
  />;
}
