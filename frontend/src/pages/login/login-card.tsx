import { ArrowRight, Eye, EyeOff, LockKeyhole, ShieldCheck, UserRound } from "lucide-react";
import { useState, type FormEvent } from "react";

import type { DemoEmployee } from "../../auth/demo-employees";
import type { AuthStatus } from "../../auth/session";
import { localizeRole } from "../../auth/principal-view";

const DEMO_PASSWORD = "CountyFlow@2026";

export function LoginCard({ employees, loading, status, error, onLogin }: {
  employees: readonly DemoEmployee[];
  loading: boolean;
  status: AuthStatus;
  error: string | null;
  onLogin: (employeeId: string) => Promise<void> | void;
}) {
  const [employeeId, setEmployeeId] = useState(() => employees[0]?.employee_id ?? "");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberAccount, setRememberAccount] = useState(true);
  const submitting = status === "authenticating";
  const selectedEmployeeId = employeeId || employees[0]?.employee_id || "";

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedEmployeeId || loading || submitting) return;
    void onLogin(selectedEmployeeId);
  };

  return <section className="county-login__card" aria-label="账号登录">
    <header className="county-login__card-tabs" role="tablist" aria-label="登录方式">
      <button type="button" role="tab" aria-selected="true" aria-controls="login-account-panel">账号登录</button>
      <button type="button" role="tab" aria-selected="false" aria-disabled="true" disabled title="当前演示环境暂未开放扫码登录">扫码登录</button>
    </header>
    <div className="county-login__welcome">
      <span><ShieldCheck size={13} /> COUNTYFLOW SECURE ACCESS</span>
      <h2>欢迎回来</h2>
      <p>登录县域物流智慧配送平台</p>
    </div>

    <form className="county-login__form" id="login-account-panel" role="tabpanel" onSubmit={submit}>
      <label className="county-login__field">
        <span className="sr-only">账号</span>
        <UserRound aria-hidden="true" />
        <select
          aria-label="切换演示员工"
          value={selectedEmployeeId}
          disabled={loading || submitting || employees.length === 0}
          onChange={(event) => setEmployeeId(event.target.value)}
        >
          {employees.length === 0 ? <option value="">账号加载中</option> : null}
          {employees.map((employee) => <option value={employee.employee_id} key={employee.employee_id}>
            {employee.display_name} · {localizeRole(employee.role)}
          </option>)}
        </select>
      </label>

      <label className="county-login__field county-login__field--password">
        <span className="sr-only">登录密码</span>
        <LockKeyhole aria-hidden="true" />
        <input aria-label="登录密码" type={showPassword ? "text" : "password"} value={DEMO_PASSWORD} readOnly />
        <button
          type="button"
          className="county-login__password-toggle"
          aria-label={showPassword ? "隐藏密码" : "显示密码"}
          onClick={() => setShowPassword((visible) => !visible)}
        >
          {showPassword ? <EyeOff /> : <Eye />}
        </button>
      </label>

      <div className="county-login__form-options">
        <label>
          <input
            aria-label="记住当前账号"
            type="checkbox"
            checked={rememberAccount}
            onChange={(event) => setRememberAccount(event.target.checked)}
          />
          <span>记住我</span>
        </label>
        <button type="button" aria-label="忘记密码" disabled title="演示账号无需找回密码">忘记密码？</button>
      </div>
      {error ? <p className="county-login__error" role="alert">{error}</p> : null}
      {status === "expired" && !error ? <p className="county-login__error" role="alert">会话已过期，请重新登录。</p> : null}
      <button className="county-login__submit" type="submit" disabled={!selectedEmployeeId || loading || submitting}>
        <span>{submitting ? "正在登录" : "登录"}</span><ArrowRight aria-hidden="true" />
      </button>
    </form>

    <footer><i /><ShieldCheck size={12}/>县域物流统一身份服务在线</footer>
  </section>;
}
