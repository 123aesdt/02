import type { Role } from "./permissions";
import type { Principal } from "./session";

export interface DemoEmployee {
  employee_id: string;
  display_name: string;
  role: Role;
}
export const FIXED_DEMO_EMPLOYEES: readonly DemoEmployee[] = [
  { employee_id: "CF-DEMO-001", display_name: "张师傅", role: "EMPLOYEE" },
  { employee_id: "CF-DEMO-006", display_name: "陈师傅", role: "EMPLOYEE" },
  { employee_id: "CF-DEMO-007", display_name: "孙调度", role: "DISPATCHER" },
  { employee_id: "CF-DEMO-003", display_name: "王主管", role: "SUPERVISOR" },
  { employee_id: "CF-DEMO-002", display_name: "李运营", role: "OPERATOR" },
  { employee_id: "CF-DEMO-004", display_name: "赵审计", role: "AUDITOR" },
  { employee_id: "CF-DEMO-005", display_name: "系统管理员", role: "ADMIN" },
];

export interface DemoEmployeeSessionResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  principal: Principal;
}
