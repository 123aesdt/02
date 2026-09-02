# Supervisor Team Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only supervisor team-task API and frontend showing real MySQL-backed task distribution for two demo dispatchers on the supervisor landing page and `/team-tasks`.

**Architecture:** Add a dedicated `workspace_reads` projection protected by `dispatch:review`; it resolves active demo dispatchers server-side and returns filtered tasks plus invariant team/member summaries. Add one typed frontend read path, reusable team components, a full page, and a compact supervisor preview without changing `/my/tasks` isolation.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Pydantic 2, pytest, React, TypeScript, Vitest, Vite, Docker Compose, MySQL.

**Spec:** `docs/superpowers/specs/2026-08-30-team-tasks-design.md`

## Global Constraints

- Team scope is only active `DemoEmployeeAccount` rows whose role is `DISPATCHER`.
- Do not add enterprise organization, department, SSO, or reporting-line models.
- Team access is read-only and requires `dispatch:review`; do not add reassignment or status mutation.
- `/api/v1/my/tasks` stays bound to the authenticated subject and accepts no other employee identifier.
- MySQL is the source of truth; do not aggregate per-employee calls in the browser or add static fallback data.
- No demo dispatchers means a successful empty team projection, never all system tasks.
- All user-facing business labels and errors are Chinese.
- Every task follows behavior-level RED, minimal implementation, GREEN.
- Preserve user changes and pre-staged files. Commit only explicit paths with `--only`. If Git identity remains absent, do not configure it; record the skipped checkpoint.
- Never read, print, return, or commit `.docker.env` values or access tokens.

## File Structure

- `backend/app/seed.py`: demo employees and deterministic demo-task assignment.
- `backend/app/workspace_reads/models.py`: framework-free team dataclasses.
- `backend/app/workspace_reads/exceptions.py`: `TeamMemberNotFound`.
- `backend/app/workspace_reads/protocols.py`: narrow repository contract.
- `backend/app/workspace_reads/sqlalchemy_repository.py`: MySQL scope, joins, counts, filters, pagination.
- `backend/app/workspace_reads/service.py`: cursor parsing and outage normalization.
- `backend/app/api/v1/workspace_read_schemas.py`: strict public response models.
- `backend/app/api/v1/workspace_reads.py`: permission, validation, error and response mapping.
- `frontend/src/types/workspace-read-models.ts`: team response/filter types.
- `frontend/src/services/api/workspace-read-client.ts`: team HTTP request.
- `frontend/src/hooks/use-workspace-reads.ts`: lifecycle and invalid-member state.
- `frontend/src/components/workspace/team-member-load.tsx`: reusable member cards.
- `frontend/src/components/workspace/team-task-table.tsx`: reusable read-only table.
- `frontend/src/pages/team-tasks-page.tsx`: filters, pagination and feedback.
- `frontend/src/pages/supervisor-workspace-page.tsx`: compact team preview.
- `frontend/src/app/router.tsx`: guarded real route.
- `frontend/src/styles/index.css`: responsive team layout.
- `frontend/e2e/team-tasks.spec.ts`: supervisor route and narrow-screen usability.

---

### Task 1: Add the second demo dispatcher and deterministic assignments

**Files:**
- Modify: `backend/app/seed.py`
- Test: `backend/tests/unit/test_seed.py`
- Test: `backend/tests/unit/test_demo_employee_seed.py`
- Test: `backend/tests/api/test_demo_employee_auth.py`
- Test: `backend/tests/security/test_demo_employee_accounts.py`

**Interfaces:**
- Produces: `DEMO_DISPATCHER_SUBJECT_IDS = ("CF-DEMO-001", "CF-DEMO-006")`.
- Produces: active account `CF-DEMO-006 / 陈调度 / DISPATCHER`.
- Preserves: only reserved `demo-seed-*` task ownership is corrected.

- [ ] **Step 1: Write failing account and seed-distribution tests**

Add the exact account tuple:

```python
("CF-DEMO-006", "陈调度", "DISPATCHER")
```

Rename the five-account test to six accounts. Replace the single-owner assertion with:

```python
assert {row.assignee_subject_id for row in tasks} == {"CF-DEMO-001", "CF-DEMO-006"}
assert sum(row.assignee_subject_id == "CF-DEMO-001" for row in tasks) == 5
assert sum(row.assignee_subject_id == "CF-DEMO-006" for row in tasks) == 5
```

For `DEMO-TASK-004`, retain `status == "REJECTED"` but expect `CF-DEMO-006`. Add a non-demo task before the second seed run and assert its owner is unchanged.

- [ ] **Step 2: Run focused tests to verify RED**

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_seed.py backend/tests/unit/test_demo_employee_seed.py backend/tests/api/test_demo_employee_auth.py backend/tests/security/test_demo_employee_accounts.py -q
```

Expected: missing `CF-DEMO-006`, six-account, and split-ownership failures.

- [ ] **Step 3: Implement the minimal seed behavior**

```python
DEMO_DISPATCHER_SUBJECT_IDS = ("CF-DEMO-001", "CF-DEMO-006")
```

Add:

```python
MappingProxyType({"employee_id": "CF-DEMO-006", "display_name": "陈调度", "role": "DISPATCHER"})
```

In `seed_demo_execution_case`:

```python
expected_assignee = DEMO_DISPATCHER_SUBJECT_IDS[(position - 1) % len(DEMO_DISPATCHER_SUBJECT_IDS)]
if task.idempotency_key == task_key:
    task.assignee_subject_id = expected_assignee
```

Do not alter status, timestamps, dispatch, audit, runtime, or unrelated tasks.

- [ ] **Step 4: Re-run Step 2 to verify GREEN**

Expected: selected tests pass; ten demo tasks split 5/5 and `REJECTED` remains unchanged.

- [ ] **Step 5: Create an isolated checkpoint if identity permits**

```powershell
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' commit --only -m "feat: add second demo dispatcher" -- backend/app/seed.py backend/tests/unit/test_seed.py backend/tests/unit/test_demo_employee_seed.py backend/tests/api/test_demo_employee_auth.py backend/tests/security/test_demo_employee_accounts.py
```

If author identity is absent, do not set it; record the skipped checkpoint.

### Task 2: Add the MySQL team-task projection

**Files:**
- Create: `backend/app/workspace_reads/exceptions.py`
- Modify: `backend/app/workspace_reads/models.py`
- Modify: `backend/app/workspace_reads/protocols.py`
- Modify: `backend/app/workspace_reads/sqlalchemy_repository.py`
- Modify: `backend/app/workspace_reads/service.py`
- Test: `backend/tests/workspace_reads/test_sqlalchemy_repository.py`

**Interfaces:**
- Consumes: `DemoEmployeeAccount`, `DispatchTask.assignee_subject_id`, `MY_TASK_STATUS_GROUPS`.
- Produces: `TeamMemberNotFound(subject_id)`.
- Produces: `list_team_tasks(*, assignee_subject_id, limit, before_id, state) -> TeamTaskPage`.
- Produces: service signature using `cursor` instead of `before_id`.

- [ ] **Step 1: Extend the fixture and write failing repository tests**

Add active `dispatcher-1`, active `dispatcher-2`, active `operator-1`, and an inactive dispatcher to `seed_workspace`. Add one task for the operator and one for the inactive dispatcher. Assert:

```python
def test_list_team_tasks_returns_only_active_dispatcher_tasks_with_invariant_summaries(sqlite_factory):
    seed_workspace(sqlite_factory)
    page = SqlAlchemyWorkspaceReadRepository(sqlite_factory).list_team_tasks(
        assignee_subject_id=None, limit=20, before_id=None, state=None
    )
    assert [item.task_id for item in page.items] == ["TASK-latest-3", "TASK-review-2", "TASK-approved-1"]
    assert page.summary == TeamTaskSummary(total=3, ready=2, waiting=1, active=0, ended=0)
    assert [(member.subject_id, member.total) for member in page.members] == [
        ("dispatcher-1", 2),
        ("dispatcher-2", 1),
    ]
```

Add a filtered test for `dispatcher-2 + READY` expecting only `TASK-latest-3`, `page.total == 1`, but invariant `summary.total == 3` and two members. Add `pytest.raises(TeamMemberNotFound)` for `operator-1`. Add two-page `limit=1` cursor coverage proving no repeated task.

Add an explicit safety regression for a database with tasks but no active demo dispatcher accounts:

```python
def test_list_team_tasks_without_demo_dispatchers_returns_safe_empty_page(sqlite_factory):
    seed_tasks_without_demo_employees(sqlite_factory)
    page = SqlAlchemyWorkspaceReadRepository(sqlite_factory).list_team_tasks(
        assignee_subject_id=None, limit=20, before_id=None, state=None
    )
    assert page.items == ()
    assert page.members == ()
    assert page.summary == TeamTaskSummary(total=0, ready=0, waiting=0, active=0, ended=0)
    assert page.total == 0
    assert page.next_cursor is None
```

This test must include at least one unrelated persisted task so it proves that an empty dispatcher scope never widens into an unrestricted task query.

- [ ] **Step 2: Run repository tests to verify RED**

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/workspace_reads/test_sqlalchemy_repository.py -q
```

Expected: missing team model, exception, and method failures.

- [ ] **Step 3: Add the exception and exact models**

```python
class TeamMemberNotFound(ValueError):
    def __init__(self, subject_id: str) -> None:
        super().__init__("team member is not an active dispatcher")
        self.subject_id = subject_id
```

```python
@dataclass(frozen=True)
class TeamTaskListItem:
    row_id: int
    task_id: str
    assignee_subject_id: str
    assignee_display_name: str
    order_no: str | None
    risk: str | None
    description: str | None
    vehicle_id: str | None
    original_route_id: str | None
    suggested_route_id: str | None
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class TeamTaskSummary:
    total: int
    ready: int
    waiting: int
    active: int
    ended: int


@dataclass(frozen=True)
class TeamMemberTaskSummary:
    subject_id: str
    display_name: str
    total: int
    ready: int
    waiting: int
    active: int
    ended: int


@dataclass(frozen=True)
class TeamTaskPage:
    items: tuple[TeamTaskListItem, ...]
    summary: TeamTaskSummary
    members: tuple[TeamMemberTaskSummary, ...]
    total: int
    next_cursor: str | None
    provenance: Literal["LIVE", "DEMO", "MIXED"] = "LIVE"
```

- [ ] **Step 4: Add the protocol and SQLAlchemy implementation**

Protocol:

```python
def list_team_tasks(
    self, *, assignee_subject_id: str | None, limit: int = 20,
    before_id: int | None, state: str | None,
) -> TeamTaskPage: ...
```

Implementation order:

1. Select active `DISPATCHER` demo accounts ordered by employee ID.
2. Reject a supplied subject not in that set with `TeamMemberNotFound`.
3. If no members exist, return zero summary, zero members, and empty items without an unrestricted task query.
4. Base-scope tasks with `assignee_subject_id.in_(member_ids)`; apply selected member and state only to items/filtered total.
5. Join the selected account for display name and reuse the latest-dispatch subquery and safe fields from `list_my_tasks`.
6. Compute team summary from base scope and member summaries for every active dispatcher, including zero-task members.
7. Order by task ID descending, fetch `limit + 1`, and use the last visible database ID as cursor.
8. Compute provenance from filtered tasks with the existing helper.

- [ ] **Step 5: Add the service method**

```python
def list_team_tasks(
    self, *, assignee_subject_id: str | None, limit: int,
    cursor: str | None, state: str | None,
) -> TeamTaskPage:
    before_id = parse_numeric_cursor(cursor)
    return self._mysql_read(lambda: self._mysql.list_team_tasks(
        assignee_subject_id=assignee_subject_id,
        limit=limit,
        before_id=before_id,
        state=state,
    ))
```

Let `TeamMemberNotFound` pass to the API; connection failures still become `WorkspaceReadUnavailable`.

- [ ] **Step 6: Re-run Step 2 to verify GREEN**

Expected: all repository tests pass, including existing owner-isolated `list_my_tasks` tests.

- [ ] **Step 7: Create an isolated checkpoint if possible**

```powershell
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' commit --only -m "feat: add team task read projection" -- backend/app/workspace_reads/exceptions.py backend/app/workspace_reads/models.py backend/app/workspace_reads/protocols.py backend/app/workspace_reads/sqlalchemy_repository.py backend/app/workspace_reads/service.py backend/tests/workspace_reads/test_sqlalchemy_repository.py
```

### Task 3: Publish the permission-protected team API

**Files:**
- Modify: `backend/app/api/v1/workspace_read_schemas.py`
- Modify: `backend/app/api/v1/workspace_reads.py`
- Test: `backend/tests/api/test_workspace_reads.py`
- Test: `backend/tests/api/test_endpoint_permissions.py`

**Interfaces:**
- Consumes: `TeamTaskPage` and `TeamMemberNotFound` from Task 2.
- Produces: `GET /api/v1/team/tasks?limit=&cursor=&state=&assignee_subject_id=`.
- Produces: strict `TeamTaskPageResponse` and `422 TEAM_MEMBER_INVALID`.

- [ ] **Step 1: Add a literal stub page and failing API tests**

Extend `StubWorkspaceReadService` with a team page containing Zhang, Chen, and one assigned task. Record calls with:

```python
def list_team_tasks(self, *, assignee_subject_id, limit, cursor, state):
    self.team_task_call = {
        "assignee_subject_id": assignee_subject_id,
        "limit": limit,
        "cursor": cursor,
        "state": state,
    }
    return self.team_tasks
```

Assert all of these behaviors:

- Supervisor request with `limit=5&state=READY&assignee_subject_id=dispatcher-1` returns exact item, summaries, members, provenance, and service call.
- Admin receives `200`.
- `TeamMemberNotFound("operator-1")` becomes `422` with `response.json()["detail"]["code"] == "TEAM_MEMBER_INVALID"`.
- `WorkspaceReadUnavailable` becomes top-level `503 WORKSPACE_READ_UNAVAILABLE`.
- Add `/api/v1/team/tasks` with `Role.DISPATCHER` to the denied-permissions table and prove zero service calls.
- Add team `state` to invalid-enum coverage and team path to invalid-cursor coverage.

- [ ] **Step 2: Run API tests to verify RED**

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/api/test_workspace_reads.py backend/tests/api/test_endpoint_permissions.py -q
```

Expected: missing schema/route failures and `404` for the team endpoint.

- [ ] **Step 3: Add strict response schemas**

```python
class TeamTaskListItemResponse(WorkspaceResponse):
    row_id: int
    task_id: str
    assignee_subject_id: str
    assignee_display_name: str
    order_no: str | None
    risk: str | None
    description: str | None
    vehicle_id: str | None
    original_route_id: str | None
    suggested_route_id: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class TeamTaskSummaryResponse(WorkspaceResponse):
    total: int
    ready: int
    waiting: int
    active: int
    ended: int


class TeamMemberTaskSummaryResponse(TeamTaskSummaryResponse):
    subject_id: str
    display_name: str


class TeamTaskPageResponse(WorkspaceResponse):
    items: list[TeamTaskListItemResponse]
    summary: TeamTaskSummaryResponse
    members: list[TeamMemberTaskSummaryResponse]
    total: int
    next_cursor: str | None
    provenance: Literal["LIVE", "DEMO", "MIXED"]
```

- [ ] **Step 4: Add the route and error mapping**

Define `TeamTasksPrincipal` with `Permission.DISPATCH_REVIEW`. Reuse `MyTaskStateFilter`; limit the optional assignee string to 128 characters.

```python
@router.get("/team/tasks", response_model=TeamTaskPageResponse)
def list_team_tasks(
    service: ServiceDependency,
    _principal: TeamTasksPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=19, pattern=r"^[0-9]+$")] = None,
    state: Annotated[MyTaskStateFilter | None, Query()] = None,
    assignee_subject_id: Annotated[str | None, Query(max_length=128)] = None,
) -> TeamTaskPageResponse | JSONResponse:
    try:
        result = service.list_team_tasks(
            assignee_subject_id=assignee_subject_id,
            limit=limit,
            cursor=cursor,
            state=state,
        )
        return TeamTaskPageResponse.model_validate(result, from_attributes=True)
    except TeamMemberNotFound as error:
        raise HTTPException(
            status_code=422,
            detail={"code": "TEAM_MEMBER_INVALID", "message": "所选调度员已不在团队。"},
        ) from error
    except InvalidWorkspaceCursor as error:
        raise HTTPException(422, detail={"code": "WORKSPACE_CURSOR_INVALID"}) from error
    except WorkspaceReadUnavailable:
        return _workspace_unavailable()
```

- [ ] **Step 5: Re-run Step 2 to verify GREEN**

Expected: selected API tests pass and denied roles never invoke the service.

- [ ] **Step 6: Run focused Ruff**

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend/app/seed.py backend/app/workspace_reads backend/app/api/v1/workspace_read_schemas.py backend/app/api/v1/workspace_reads.py backend/tests/unit/test_seed.py backend/tests/unit/test_demo_employee_seed.py backend/tests/workspace_reads/test_sqlalchemy_repository.py backend/tests/api/test_workspace_reads.py backend/tests/api/test_endpoint_permissions.py
```

Expected: exit code 0.

- [ ] **Step 7: Create an isolated checkpoint if possible**

```powershell
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' commit --only -m "feat: expose supervisor team tasks" -- backend/app/api/v1/workspace_read_schemas.py backend/app/api/v1/workspace_reads.py backend/tests/api/test_workspace_reads.py backend/tests/api/test_endpoint_permissions.py
```

### Task 4: Add the typed frontend team read path

**Files:**
- Modify: `frontend/src/types/workspace.ts`
- Modify: `frontend/src/types/workspace-read-models.ts`
- Modify: `frontend/src/services/api/workspace-read-client.ts`
- Modify: `frontend/src/hooks/use-workspace-reads.ts`
- Test: `frontend/tests/workspace-read-client.test.ts`
- Test: `frontend/tests/workspace-read-hooks.test.tsx`

**Interfaces:**
- Consumes: Task 3 fields and `TEAM_MEMBER_INVALID`.
- Produces: `workspaceReadClient.getTeamTasks(filters, signal)`.
- Produces: `useTeamTasksRead(filters)`.
- Produces: read state `INVALID_FILTER` only for the team-member `422`.

- [ ] **Step 1: Write failing client and hook tests**

Add a `teamTaskPage` fixture matching Task 3. Assert:

```ts
await expect(client.getTeamTasks({
  limit: 5,
  cursor: "9",
  state: "ACTIVE",
  assignee_subject_id: "CF-DEMO-006",
})).resolves.toEqual(teamTaskPage);
expect(fetchImpl).toHaveBeenCalledWith(
  "http://api.test/api/v1/team/tasks?limit=5&cursor=9&state=ACTIVE&assignee_subject_id=CF-DEMO-006",
  expect.objectContaining({ credentials: "same-origin" }),
);
```

Hook assertions: exact parameters; an empty successful page remains `READY` with zero data; `403 -> FORBIDDEN`; `503 -> UNAVAILABLE`; `ApiError(422, "TEAM_MEMBER_INVALID", "invalid") -> INVALID_FILTER`.

- [ ] **Step 2: Run frontend read tests to verify RED**

```powershell
Set-Location frontend
npm test -- workspace-read-client.test.ts workspace-read-hooks.test.tsx
```

Expected: missing team types, method, hook, and state failures.

- [ ] **Step 3: Add exact TypeScript types**

```ts
export interface TeamTaskListItem extends MyTaskListItem {
  assignee_subject_id: string;
  assignee_display_name: string;
}

export interface TeamMemberTaskSummary extends MyTaskSummary {
  subject_id: string;
  display_name: string;
}

export interface TeamTaskPageResponse extends PageResponse<TeamTaskListItem> {
  summary: MyTaskSummary;
  members: TeamMemberTaskSummary[];
}

export interface TeamTaskFilters extends MyTaskFilters {
  assignee_subject_id?: string;
}
```

Add `"INVALID_FILTER"` to `ReadStateName`.

- [ ] **Step 4: Add the client method and hook**

```ts
getTeamTasks(filters?: TeamTaskFilters, signal?: AbortSignal): Promise<TeamTaskPageResponse>;

async getTeamTasks(filters: TeamTaskFilters = {}, signal?: AbortSignal): Promise<TeamTaskPageResponse> {
  return this.requestPage("/api/v1/team/tasks", filters, signal);
}
```

Before the generic error branch:

```ts
if (error instanceof ApiError && error.status === 422 && error.code === "TEAM_MEMBER_INVALID") {
  return { state: "INVALID_FILTER", data: null };
}
```

Do not use an empty predicate; preserve literal zero summaries:

```ts
export function useTeamTasksRead(filters: TeamTaskFilters = {}): WorkspaceReadHookState<TeamTaskPageResponse> {
  const { limit, cursor, state, assignee_subject_id } = filters;
  const request = useCallback(
    (signal: AbortSignal) => workspaceReadClient.getTeamTasks(
      withoutEmptyFilters({ limit, cursor, state, assignee_subject_id }), signal,
    ),
    [limit, cursor, state, assignee_subject_id],
  );
  return useWorkspaceRead(request, [limit, cursor, state, assignee_subject_id]);
}
```

- [ ] **Step 5: Re-run Step 2 to verify GREEN**

Expected: selected tests pass without unhandled React updates.

- [ ] **Step 6: Create an isolated checkpoint if possible**

```powershell
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' commit --only -m "feat: add team task frontend client" -- frontend/src/types/workspace.ts frontend/src/types/workspace-read-models.ts frontend/src/services/api/workspace-read-client.ts frontend/src/hooks/use-workspace-reads.ts frontend/tests/workspace-read-client.test.ts frontend/tests/workspace-read-hooks.test.tsx
```

### Task 5: Replace the team-tasks placeholder with the full read-only page

**Files:**
- Create: `frontend/src/components/workspace/team-member-load.tsx`
- Create: `frontend/src/components/workspace/team-task-table.tsx`
- Create: `frontend/src/pages/team-tasks-page.tsx`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/styles/index.css`
- Create: `frontend/tests/team-tasks-page.test.tsx`
- Modify: `frontend/tests/role-routes.test.tsx`
- Create: `frontend/e2e/team-tasks.spec.ts`

**Interfaces:**
- Consumes: `useTeamTasksRead`, `TeamTaskListItem`, `TeamMemberTaskSummary`.
- Produces: `TeamMemberLoad`, `TeamTaskTable`, and guarded `/team-tasks`.

- [ ] **Step 1: Write failing page and route tests**

Create a fixture with Zhang and Chen summaries and one task for each. Assert heading “团队任务”, five summary metrics, both member cards, table column “负责人”, Chinese status labels, and detail links for both tasks. Assert no text matching `重新分配|修改状态|批量操作`.

Click the Chen selector and expect `assignee_subject_id: "CF-DEMO-006"`. Click “处理中” and expect `state: "ACTIVE"`. Both actions reset cursor history. Add exact next/previous pagination assertions.

Add feedback tests for `403`, `503`, generic errors, successful zero data, and `INVALID_FILTER`. The invalid-member view says “所选调度员已不在团队”; clicking “清除筛选” requests again without `assignee_subject_id`.

In `role-routes.test.tsx`, add `getTeamTasks` to the mock. Prove `dispatch:review` renders the real page and calls it, while `dispatch:read` renders “无权访问” and makes no call.

- [ ] **Step 2: Run page and route tests to verify RED**

```powershell
Set-Location frontend
npm test -- team-tasks-page.test.tsx role-routes.test.tsx
```

Expected: missing page/components and current placeholder text failures.

- [ ] **Step 3: Build reusable member and task components**

Public props:

```ts
export function TeamMemberLoad(
  { members }: { members: readonly TeamMemberTaskSummary[] },
): React.JSX.Element;

export function TeamTaskTable({
  items, caption, emptyTitle,
}: {
  items: readonly TeamTaskListItem[];
  caption: string;
  emptyTitle: string;
}): React.JSX.Element;
```

Member cards show name, employee ID, total, ready, waiting, active, ended. The table reuses `DataTable`, `StatusBadge`, `localizeStatus`, and `Link`; columns are task, owner, order, risk, description, vehicle, suggested route, status, update time, operation.

- [ ] **Step 4: Build the page state machine**

Use separate `assignee`, `state`, `cursor`, and `history` state. Switching assignee or state sets cursor to `null` and history to `[]`. Render `OperationalSummary` from `summary`, member cards from `members`, and the table from `items`.

Use `<select aria-label="调度员筛选">` populated only from response members; state buttons are “全部、待执行、等待中、处理中、已结束”. Do not hard-code employee names in production component code.

Feedback copy is exact:

- `FORBIDDEN`: “没有查看团队任务的权限”.
- `UNAVAILABLE`: “团队任务服务暂不可用”.
- `INVALID_FILTER`: “所选调度员已不在团队”.
- `ERROR`: “团队任务加载失败”.
- successful empty items: “当前筛选条件下没有团队任务”.

- [ ] **Step 5: Replace only the placeholder route**

```tsx
{ path: "team-tasks", element: <RequirePermission permission="dispatch:review"><TeamTasksPage /></RequirePermission> },
```

Do not alter navigation permissions or unrelated routes.

- [ ] **Step 6: Add responsive token-based styles**

Add `.team-member-load` grid, token-based member cards, and a wrapping `.team-task-filters` row with controls at least 36px high. At `max-width:600px`, use one member column and a full-width select while retaining the existing horizontally scrollable table.

- [ ] **Step 7: Add a narrow-screen browser regression**

Follow the existing authenticated demo-session E2E setup. Open `/team-tasks` as 王主管 at a `390x844` viewport, then assert the heading, dispatcher selector, state filters, summary, member cards, task table, and “查看详情” link remain reachable. Assert the document itself has no horizontal overflow:

```ts
expect(await page.evaluate(() =>
  document.documentElement.scrollWidth <= document.documentElement.clientWidth
)).toBe(true);
```

If the data table is wider than the viewport, assert only its existing scroll container scrolls horizontally and that scrolling exposes the final operation column.

- [ ] **Step 8: Re-run focused tests to verify GREEN**

```powershell
Set-Location frontend
npm test -- team-tasks-page.test.tsx role-routes.test.tsx
npm run test:e2e -- e2e/team-tasks.spec.ts
```

Expected: page and route tests pass.

- [ ] **Step 9: Create an isolated checkpoint if possible**

```powershell
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' commit --only -m "feat: add supervisor team tasks page" -- frontend/src/components/workspace/team-member-load.tsx frontend/src/components/workspace/team-task-table.tsx frontend/src/pages/team-tasks-page.tsx frontend/src/app/router.tsx frontend/src/styles/index.css frontend/tests/team-tasks-page.test.tsx frontend/tests/role-routes.test.tsx frontend/e2e/team-tasks.spec.ts
```

### Task 6: Add the supervisor-home team preview

**Files:**
- Modify: `frontend/src/pages/supervisor-workspace-page.tsx`
- Test: `frontend/tests/supervisor-workspace.test.tsx`

**Interfaces:**
- Consumes: `useTeamTasksRead({ limit: 5 })`, `OperationalSummary`, `TeamMemberLoad`, `TeamTaskTable`.
- Produces: `supervisor-team-tasks` section and `/team-tasks` link.
- Preserves: independent review, runtime, and intervention reads.

- [ ] **Step 1: Write failing preview tests**

Add and reset `getTeamTasks` in the hoisted mock. Extend `prepareLiveReads` with the two-member team fixture. Assert:

```ts
expect(workspaceReadApi.getTeamTasks).toHaveBeenCalledWith(
  { limit: 5 }, expect.any(AbortSignal),
);
```

Assert “团队任务”, “团队概览”, all five invariant summary metrics, both employee load values, recent task owners, and `a[href="/team-tasks"]` with “查看全部团队任务”. Assert old placeholder absence. A team `503` must show “团队任务服务暂不可用” while review/runtime remain visible; retry refreshes only the team read.

- [ ] **Step 2: Run supervisor tests to verify RED**

```powershell
Set-Location frontend
npm test -- supervisor-workspace.test.tsx
```

Expected: missing call and preview failures.

- [ ] **Step 3: Add the independently failing preview**

Call `useTeamTasksRead({ limit: 5 })`. After the risk overview and before review handling, add:

```tsx
<WorkspaceSection
  id="supervisor-team-tasks"
  title="团队任务"
  description="仅汇总启用调度员的真实任务归属与状态。"
  actions={<Link to="/team-tasks">查看全部团队任务</Link>}
>
  {team.state === "READY" && team.data
    ? <>
        <OperationalSummary
          title="团队概览"
          metrics={toTeamSummaryMetrics(team.data.summary)}
        />
        <TeamMemberLoad members={team.data.members} />
        <TeamTaskTable
          items={team.data.items}
          caption="最近团队任务"
          emptyTitle="当前没有团队任务"
        />
      </>
    : <SupervisorTeamFeedback state={team.state} onRetry={team.refresh} />}
</WorkspaceSection>
```

Add a small pure `toTeamSummaryMetrics` adapter using the same Chinese labels as the full page: “任务总数、待执行、等待中、处理中、已结束”. `SupervisorTeamFeedback` has team-specific loading, permission, unavailable, invalid-filter, and generic error copy. It must not read or change review/runtime state.

- [ ] **Step 4: Re-run Step 2 to verify GREEN**

Expected: all supervisor tests pass, including prior review/runtime tests.

- [ ] **Step 5: Create an isolated checkpoint if possible**

```powershell
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' commit --only -m "feat: show team tasks on supervisor home" -- frontend/src/pages/supervisor-workspace-page.tsx frontend/tests/supervisor-workspace.test.tsx
```

### Task 7: Full verification and local runtime smoke test

**Files:**
- Verify only. If a command exposes a regression, return to that task's RED/GREEN cycle before editing.

**Interfaces:**
- Consumes: Tasks 1–6.
- Produces: command evidence and rebuilt local runtime.

- [ ] **Step 1: Run backend full verification**

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest -q
```

Expected: Ruff exit 0 and zero pytest failures. Report skip count exactly.

- [ ] **Step 2: Run frontend full verification**

```powershell
Set-Location frontend
npm test
npm run lint
npm run build
```

Expected: all tests pass, lint has zero errors, build exits 0. Report existing warnings separately.

- [ ] **Step 3: Run Docker-backed MySQL integration**

Locate the project target:

```powershell
rg -n "integration|mysql" backend/tests Makefile
```

Run the existing MySQL integration command found there. Do not replace it with SQLite. If only a complete integration target exists, run that target and record exact output.

- [ ] **Step 4: Rebuild the verified runtime**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-full.ps1
```

Expected: backend, frontend, workers, MySQL, Redis, Qdrant, Neo4j, Prometheus, and Grafana become ready. Never print `.docker.env`.

- [ ] **Step 5: Smoke-test live permissions without printing tokens**

Create demo sessions for `CF-DEMO-003`, `CF-DEMO-001`, and `CF-DEMO-006` with `Invoke-RestMethod`; retain tokens only in variables and output only assertions:

```text
王主管 /api/v1/team/tasks -> 200, members=2, total=10
张调度 /api/v1/team/tasks -> 403
张调度 /api/v1/my/tasks -> 200, summary.total=5
陈调度 /api/v1/my/tasks -> 200, summary.total=5
```

Request `http://localhost:5173`, assert `200`, and confirm its served bundle contains “团队任务服务暂不可用” but not “团队任务读取接口尚未开放”.

- [ ] **Step 6: Run final whitespace and scope checks**

```powershell
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' diff --check
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' status --short
```

Expected: `diff --check` exit 0. Inspect every changed path; confirm no secret, `.docker.env`, unrelated file, or user-staged file entered scope.
