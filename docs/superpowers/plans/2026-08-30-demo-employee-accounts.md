# 免密演示员工账号 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本地展示环境中提供五个 MySQL 持久化的免密员工账号，并支持前端安全选择、切换和退出。

**Architecture:** `demo_employee_accounts` 是演示身份的唯一来源；SQLAlchemy 仓储向会话服务暴露窄读取接口，会话服务再调用现有开发 JWT 签发器。React 认证提供器只提交员工编号并在内存保存返回令牌，角色和权限始终由服务端账号记录决定。

**Tech Stack:** FastAPI、SQLAlchemy 2、Alembic、MySQL、PyJWT、React 18、TypeScript、Vitest、React Testing Library、Vite。

**Spec:** `docs/superpowers/specs/2026-08-30-demo-employee-accounts-design.md`

## Global Constraints

- 仅在 `local`、`docker-dev`、`test` 且认证提供器为 `development_jwt` 时开放免密账号能力。
- 不新增密码、邮箱、手机号、Cookie 或浏览器持久令牌。
- 角色必须由数据库账号派生，客户端不得提交角色。
- API 模式失败时不得回退模拟身份或模拟权限。
- 当前工作树含大量既有未提交文件；本次只修改计划列出的文件，不执行 Git 提交。
- 每个实现任务遵循失败测试、最小实现、通过测试的 TDD 顺序。

---

### Task 1: 演示员工数据模型与幂等种子

**Files:**
- Create: `backend/app/models/demo_employee_account.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260830_07_demo_employee_accounts.py`
- Modify: `backend/app/seed.py`
- Create: `backend/tests/unit/test_demo_employee_seed.py`

**Interfaces:**
- Produces: `DemoEmployeeAccount(employee_id, display_name, role, is_active)`。
- Produces: `seed_demo_employee_accounts(session: Session) -> None`。

- [ ] **Step 1: Write the failing seed behavior test**

```python
def test_demo_employee_seed_creates_five_distinct_roles(session):
    seed_demo_employee_accounts(session)
    accounts = session.scalars(select(DemoEmployeeAccount).order_by(DemoEmployeeAccount.employee_id)).all()
    assert [(item.employee_id, item.display_name, item.role) for item in accounts] == [
        ("CF-DEMO-001", "张调度", "DISPATCHER"),
        ("CF-DEMO-002", "李运营", "OPERATOR"),
        ("CF-DEMO-003", "王主管", "SUPERVISOR"),
        ("CF-DEMO-004", "赵审计", "AUDITOR"),
        ("CF-DEMO-005", "系统管理员", "ADMIN"),
    ]
```

- [ ] **Step 2: Run the test and confirm missing model/seed failure**

Run: `cd backend && pytest tests/unit/test_demo_employee_seed.py -q`

- [ ] **Step 3: Implement the model, migration and idempotent seed**

Create a primary-key employee number, constrained non-null display name/role, active flag defaulting true, and timestamp fields. Call `seed_demo_employee_accounts()` from `seed_database()` before the existing business-case seed.

- [ ] **Step 4: Run focused model/seed tests**

Run: `cd backend && pytest tests/unit/test_demo_employee_seed.py tests/unit/test_seed.py -q`

- [ ] **Step 5: Check the migration and diff**

Run: `cd backend && alembic upgrade head`

Run: `git -c safe.directory=C:/Users/24090/OneDrive/Desktop/县域物流识别异常 diff --check`

### Task 2: 服务器派生角色的演示会话服务

**Files:**
- Create: `backend/app/security/demo_employee_accounts.py`
- Modify: `backend/app/security/development_session.py`
- Create: `backend/tests/security/test_demo_employee_accounts.py`

**Interfaces:**
- Produces: `DemoEmployee(employee_id: str, display_name: str, role: Role)`。
- Produces: `DemoEmployeeAccountRepository.list_active() -> tuple[DemoEmployee, ...]`。
- Produces: `DemoEmployeeAccountRepository.get_active(employee_id: str) -> DemoEmployee | None`。
- Produces: `DemoEmployeeSessionService.list_accounts()` and `issue(employee_id)`。
- Produces: `DevelopmentSessionIssuer.issue_identity(subject_id, display_name, role)`。

- [ ] **Step 1: Write failing service tests**

```python
def test_issue_uses_repository_role_instead_of_client_role():
    service = DemoEmployeeSessionService(repository, issuer)
    session = service.issue("CF-DEMO-001")
    assert session.principal.subject_id == "CF-DEMO-001"
    assert session.principal.display_name == "张调度"
    assert session.principal.roles == frozenset({Role.DISPATCHER})

def test_unknown_or_inactive_employee_cannot_receive_session():
    with pytest.raises(DemoEmployeeNotFound):
        service.issue("CF-DEMO-999")
```

- [ ] **Step 2: Run and observe missing service failure**

Run: `cd backend && pytest tests/security/test_demo_employee_accounts.py -q`

- [ ] **Step 3: Implement repository, service and identity-aware JWT issue method**

Normalize employee ids with trim + uppercase, query only active rows, map the stored role through `Role`, and build permissions from `ROLE_PERMISSION_MATRIX`.

- [ ] **Step 4: Run focused service and JWT tests**

Run: `cd backend && pytest tests/security/test_demo_employee_accounts.py tests/security/test_jwt_provider.py -q`

- [ ] **Step 5: Check formatting and diff**

Run: `ruff check backend/app/security backend/tests/security`

Run: `git -c safe.directory=C:/Users/24090/OneDrive/Desktop/县域物流识别异常 diff --check`

### Task 3: 开发环境账号列表与免密会话 API

**Files:**
- Modify: `backend/app/api/v1/auth_schemas.py`
- Modify: `backend/app/api/v1/auth.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/api/test_authentication.py`

**Interfaces:**
- Produces: `GET /api/v1/auth/demo-employees`。
- Produces: `POST /api/v1/auth/demo-session` with `{employee_id: string}`。
- Consumes: `DemoEmployeeSessionService` from Task 2。

- [ ] **Step 1: Write failing API contract tests**

```python
def test_demo_session_uses_employee_record_role(client):
    response = client.post("/api/v1/auth/demo-session", json={"employee_id": "CF-DEMO-001"})
    assert response.status_code == 200
    assert response.json()["principal"]["roles"] == ["DISPATCHER"]

def test_demo_accounts_are_hidden_in_production(client):
    client.app.state.runtime_profile = "production"
    assert client.get("/api/v1/auth/demo-employees").status_code == 404
    assert client.post("/api/v1/auth/demo-session", json={"employee_id": "CF-DEMO-001"}).status_code == 404
```

- [ ] **Step 2: Run and observe 404 route failures**

Run: `cd backend && pytest tests/api/test_authentication.py -q`

- [ ] **Step 3: Implement schemas, routes and app-state service wiring**

Return only employee id, display name and role from list responses. Convert unknown/inactive employees to the same `NOT_FOUND` response. Instantiate the SQLAlchemy repository only for allowed runtime profiles and development JWT authentication.

- [ ] **Step 4: Run authentication and security tests**

Run: `cd backend && pytest tests/api/test_authentication.py tests/security -q`

- [ ] **Step 5: Run backend static checks**

Run: `ruff check backend`

Run: `git -c safe.directory=C:/Users/24090/OneDrive/Desktop/县域物流识别异常 diff --check`

### Task 4: 前端演示员工会话状态与 API 适配

**Files:**
- Create: `frontend/src/auth/demo-employees.ts`
- Modify: `frontend/src/auth/auth-state.ts`
- Modify: `frontend/src/auth/auth-provider.tsx`
- Modify: `frontend/src/auth/auth-session-banner.tsx`
- Modify: `frontend/tests/auth-session.test.tsx`

**Interfaces:**
- Produces: `DemoEmployee { employee_id, display_name, role }`。
- Produces: `AuthContextValue.demoEmployees`、`demoEmployeesLoading`、`switchDemoEmployee(employeeId)`。

- [ ] **Step 1: Replace the automatic-admin expectation with failing employee-list behavior tests**

```tsx
it("loads demo employees without automatically issuing a privileged session", async () => {
  render(<AuthProvider><Probe /></AuthProvider>);
  await waitFor(() => expect(screen.getByText("张调度")).toBeInTheDocument());
  expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/demo-employees"), expect.anything());
  expect(fetch).not.toHaveBeenCalledWith(expect.stringContaining("/demo-session"), expect.anything());
});

it("posts only the selected employee id and keeps the token in memory", async () => {
  await user.click(screen.getByRole("option", { name: /张调度/ }));
  expect(JSON.parse(fetch.mock.calls.at(-1)[1].body)).toEqual({ employee_id: "CF-DEMO-001" });
  expect(getSessionSnapshot().principal?.roles).toEqual(["DISPATCHER"]);
});
```

- [ ] **Step 2: Run and observe the old automatic-session behavior fail**

Run: `cd frontend && npm test -- --run tests/auth-session.test.tsx`

- [ ] **Step 3: Implement employee loading and selection**

Start the list request once in development JWT API mode, retain the list independently from session state, post only `employee_id`, and keep the returned token in the existing memory-only session store.

- [ ] **Step 4: Run focused authentication tests**

Run: `cd frontend && npm test -- --run tests/auth-session.test.tsx`

- [ ] **Step 5: Run lint and diff checks**

Run: `cd frontend && npm run lint`

Run: `git -c safe.directory=C:/Users/24090/OneDrive/Desktop/县域物流识别异常 diff --check`

### Task 5: 顶部员工切换器与中文演示状态

**Files:**
- Create: `frontend/src/auth/demo-employee-switcher.tsx`
- Modify: `frontend/src/components/app-shell.tsx`
- Modify: `frontend/src/styles/light-migration.css`
- Create: `frontend/tests/demo-employee-switcher.test.tsx`
- Modify: `frontend/tests/app-shell-light.test.ts`

**Interfaces:**
- Consumes: Task 4 `AuthContextValue` employee fields。
- Produces: accessible “选择演示员工” combobox and switch action。

- [ ] **Step 1: Write failing interaction and accessibility tests**

```tsx
it("switches to the selected employee and labels the identity as demo", async () => {
  render(<DemoEmployeeSwitcher employees={employees} currentEmployeeId={null} onSelect={onSelect} />);
  await user.selectOptions(screen.getByRole("combobox", { name: "切换演示员工" }), "CF-DEMO-003");
  expect(onSelect).toHaveBeenCalledWith("CF-DEMO-003");
  expect(screen.getByText("演示身份")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run and observe missing component failure**

Run: `cd frontend && npm test -- --run tests/demo-employee-switcher.test.tsx tests/app-shell-light.test.ts`

- [ ] **Step 3: Implement the switcher and authenticated/anonymous banner copy**

Render the switcher in the top bar for development JWT API mode, navigate to `/` after a successful switch, keep the current employee selected, and expose an enabled “退出” action that clears the session.

- [ ] **Step 4: Run focused UI tests**

Run: `cd frontend && npm test -- --run tests/demo-employee-switcher.test.tsx tests/app-shell-light.test.ts tests/role-navigation.test.ts`

- [ ] **Step 5: Build the frontend**

Run: `cd frontend && npm run build`

### Task 6: Docker 演示验收与全量回归

**Files:**
- Modify: `frontend/e2e/security-auth.spec.ts`
- Modify: `frontend/e2e/support/security-auth.ts`
- Modify: `docs/verification/frontend-role-ui/frontend-role-light-review.md`

**Interfaces:**
- Consumes: Tasks 1-5 complete feature surface。
- Produces: repeatable browser proof for account selection and role-specific navigation。

- [ ] **Step 1: Add a failing browser flow for five seeded accounts**

Use `CF-DEMO-001` to verify dispatcher navigation, then switch to `CF-DEMO-005` and verify system overview access. Assert no password input exists and the page visibly says “演示身份”.

- [ ] **Step 2: Run the focused E2E and observe the old helper fail**

Run: `cd frontend && npx playwright test e2e/security-auth.spec.ts`

- [ ] **Step 3: Update the E2E authentication helper to select a seeded employee**

Map requested roles to the fixed employee ids and select the employee through the public UI or `/demo-session`; never post a role to the new endpoint.

- [ ] **Step 4: Run required project verification**

Run: `ruff check backend`

Run: `cd backend && pytest -q`

Run: `cd frontend && npm run lint && npm test -- --run && npm run build`

Run targeted Docker integration against real MySQL and Redis using the repository's existing integration test command.

- [ ] **Step 5: Run final whitespace and scope checks**

Run: `git -c safe.directory=C:/Users/24090/OneDrive/Desktop/县域物流识别异常 diff --check`

Inspect: `git -c safe.directory=C:/Users/24090/OneDrive/Desktop/县域物流识别异常 diff -- backend frontend docs/superpowers docs/verification`
