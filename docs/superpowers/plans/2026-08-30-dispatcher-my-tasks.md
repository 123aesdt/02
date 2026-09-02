# Dispatcher My Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real employee-owned task queue for the passwordless dispatcher and reuse it on the dispatcher workspace.

**Architecture:** Add an indexed assignee subject to `DispatchTask`, expose a narrow principal-scoped MySQL read model through the existing workspace read service, then consume the contract from a dedicated React page and the dispatcher summary. The server derives ownership from the authenticated principal and never accepts a client-selected employee id.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, MySQL 8.4, React, TypeScript, Vitest, Playwright, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-30-dispatcher-my-tasks-design.md`

## Global Constraints

- Use MySQL as the task source of truth; do not fabricate frontend data.
- Keep `assignee_subject_id` nullable and maximum 128 characters.
- Filter ownership with the authenticated principal subject on the server.
- Preserve current demo review decisions and task statuses during seed backfill.
- Require `dispatch:read`; operators and auditors remain forbidden.
- Follow strict RED → GREEN → REFACTOR for each behavior.
- Preserve the current dirty, unborn worktree; do not stage or commit user files.

---

### Task 1: Persist task ownership and backfill the local demo

**Files:**
- Create: `backend/alembic/versions/20260830_08_dispatch_task_assignee.py`
- Modify: `backend/app/models/task.py`
- Modify: `backend/app/seed.py`
- Modify: `backend/tests/unit/test_models.py`
- Modify: `backend/tests/unit/test_seed.py`

**Interfaces:**
- Produces: `DispatchTask.assignee_subject_id: Mapped[str | None]`.
- Produces: development seed assignment `DEMO-TASK-* -> CF-DEMO-001`.

- [ ] Write a model test asserting the field accepts a subject id and a seed test proving an existing task is assigned without changing its status.
- [ ] Run the two targeted tests and confirm they fail because the field is absent.
- [ ] Add revision `20260830_08` after `20260830_07`, nullable `VARCHAR(128)`, and index `ix_dispatch_tasks_assignee_created_at` on assignee plus created time.
- [ ] Add the ORM field/index and idempotent seed backfill after task lookup/creation.
- [ ] Rerun the targeted tests and confirm they pass.

### Task 2: Add the principal-scoped MySQL read model

**Files:**
- Modify: `backend/app/workspace_reads/models.py`
- Modify: `backend/app/workspace_reads/protocols.py`
- Modify: `backend/app/workspace_reads/sqlalchemy_repository.py`
- Modify: `backend/app/workspace_reads/service.py`
- Modify: `backend/tests/workspace_reads/test_sqlalchemy_repository.py`

**Interfaces:**
- Produces: `MyTaskListItem`, `MyTaskSummary`, and `MyTaskPage`.
- Produces: `WorkspaceReadRepository.list_my_tasks(*, subject_id, limit, before_id, state)`.
- Produces: `WorkspaceReadService.list_my_tasks(*, subject_id, limit, cursor, state)`.

- [ ] Write repository tests proving exact subject isolation, latest-dispatch selection, summary counts independent of filtering, state filtering, and pagination.
- [ ] Run the repository tests and confirm missing interfaces fail.
- [ ] Implement status-group constants and a single read-only SQL projection joining task, order, anomaly, and latest dispatch.
- [ ] Extend the protocol and service with numeric cursor parsing and existing connection-failure normalization.
- [ ] Rerun workspace-read repository and service tests.

### Task 3: Expose the authenticated `/api/v1/my/tasks` contract

**Files:**
- Modify: `backend/app/api/v1/workspace_read_schemas.py`
- Modify: `backend/app/api/v1/workspace_reads.py`
- Modify: `backend/tests/api/test_workspace_reads.py`
- Modify: `backend/tests/api/test_endpoint_permissions.py`

**Interfaces:**
- Produces: `GET /api/v1/my/tasks?limit=&cursor=&state=` returning `MyTaskPageResponse`.
- Consumes: `principal.subject_id` and `Permission.DISPATCH_READ`.

- [ ] Write API tests asserting the principal subject is forwarded, dispatcher/admin access works, operator/auditor access is forbidden, invalid cursor is 422, and unavailable MySQL is 503.
- [ ] Run targeted API tests and confirm 404/missing schema failures.
- [ ] Add strict response schemas, queue-state query literal, dependency permission, and route mapping.
- [ ] Rerun targeted API and permission tests.

### Task 4: Build the API client and React data hook

**Files:**
- Modify: `frontend/src/types/workspace-read-models.ts`
- Modify: `frontend/src/services/api/workspace-read-client.ts`
- Modify: `frontend/src/hooks/use-workspace-reads.ts`
- Modify: `frontend/tests/workspace-read-client.test.ts`
- Modify: `frontend/tests/workspace-read-hooks.test.tsx`

**Interfaces:**
- Produces: `MyTaskListItem`, `MyTaskSummary`, `MyTaskPageResponse`, `MyTaskFilters`.
- Produces: `workspaceReadClient.getMyTasks(filters, signal)`.
- Produces: `useMyTasksRead(filters)`.

- [ ] Write client tests for `/api/v1/my/tasks` serialization and hook tests for READY, EMPTY, refresh, and cancellation behavior.
- [ ] Run targeted Vitest files and confirm missing client/hook failures.
- [ ] Add the types, client method, and primitive-dependency hook.
- [ ] Rerun the two targeted Vitest files.

### Task 5: Replace `/my-tasks` placeholder with the real task page

**Files:**
- Create: `frontend/src/pages/my-tasks-page.tsx`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/styles/light-migration.css`
- Create: `frontend/tests/my-tasks-page.test.tsx`
- Modify: `frontend/tests/role-routes.test.tsx`

**Interfaces:**
- Consumes: `useMyTasksRead` and `/dispatch/:taskId`.
- Produces: summary, filters, task table, pagination, and explicit read states.

- [ ] Write page tests for real rows, Chinese status text, filter request changes, detail links, summary counts, empty/forbidden/unavailable states, and no static demo fallback.
- [ ] Run page and route tests and confirm the placeholder/missing page failures.
- [ ] Implement `MyTasksPage`, replace the `NotExposedPage` route, and add responsive styles.
- [ ] Rerun page and route tests.

### Task 6: Reuse the projection on the dispatcher workspace

**Files:**
- Modify: `frontend/src/pages/dispatcher-workspace-page.tsx`
- Modify: `frontend/src/components/workspace/task-queue.tsx`
- Modify: `frontend/tests/dispatcher-workspace.test.tsx`

**Interfaces:**
- Consumes: `useMyTasksRead({ limit: 5 })`.
- Produces: real overview metrics and a five-row linked task queue.

- [ ] Replace the old unavailable assertion with failing tests for returned metrics/tasks and unavailable-state honesty.
- [ ] Run the dispatcher workspace test and confirm failure against the empty array implementation.
- [ ] Map the API summary and items into existing workspace components, adding task-detail links without introducing duplicate fetching.
- [ ] Rerun the dispatcher workspace test.

### Task 7: Full verification and real demo acceptance

**Files:**
- Create: `docs/verification/dispatcher-my-tasks.md`

**Interfaces:**
- Verifies: schema migration, API ownership, rendered page, Docker runtime, and remaining dispatcher-page gaps.

- [ ] Run `ruff check backend` and the complete backend Pytest suite.
- [ ] Run frontend ESLint, all Vitest tests, and production build.
- [ ] Run `scripts/start-full.ps1` and confirm migration exit code 0 plus ten long-running healthy services.
- [ ] Use passwordless `CF-DEMO-001` to verify real tasks and use another principal to prove no ownership leak.
- [ ] Use Playwright because the Browser plugin is not available; verify `/my-tasks`, a filter interaction, a detail link, desktop/mobile layout, and console health. Save temporary evidence outside the repo.
- [ ] Inspect dispatcher-role pages for remaining unexposed sections and record them as intentional follow-up scope, not fabricated data.
- [ ] Run `git -c safe.directory=<workspace> diff --check` and record the actual output.
