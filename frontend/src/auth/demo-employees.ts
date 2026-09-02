import type { Role } from "./permissions";
import type { Principal } from "./session";

export interface DemoEmployee {
  employee_id: string;
  display_name: string;
  role: Role;
}

export interface DemoEmployeeSessionResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  principal: Principal;
}
