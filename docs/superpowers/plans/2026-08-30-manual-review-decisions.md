# Manual Review Decisions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为本地演示环境提供真实、可审计、权限受控的人工复核批准/拒绝闭环。

**Architecture:** 新建单一职责的复核决定服务，在一个 MySQL 事务中锁定任务、更新带版本锁的调度并追加领域审计记录；FastAPI 路由只负责验证、鉴权和错误映射。React 页面通过独立 API 客户端提交决定，成功后重新读取服务端列表。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy 2、MySQL、Pytest、React、TypeScript、Vitest。

**Spec:** `docs/superpowers/specs/2026-08-30-manual-review-decisions-design.md`

## Global Constraints

- MySQL 是任务、调度和审计数据的唯一事实来源。
- `Dispatch.version` 必须继续使用 SQLAlchemy `version_id_col`，`StaleDataError` 转换为 HTTP 409。
- 身份来自服务端 `AuthenticatedPrincipal`，不得接受客户端提交的复核人。
- 不触发 Redis、Worker 或 LangGraph；不接企业数据；不记录令牌、密钥或授权头。
- 所有功能变更遵循失败测试 → 最小实现 → 通过测试。
- 当前仓库没有首个提交且包含用户改动；不创建提交，只在每个阶段检查差异。

---

### Task 1: 后端复核领域服务

**Files:**
- Create: `backend/app/reviews/models.py`
- Create: `backend/app/reviews/service.py`
- Test: `backend/tests/reviews/test_service.py`

**Interfaces:**
- Consumes: `session_factory`, `AuthenticatedPrincipal`, `DispatchTask`, `Dispatch`, `AuditRecord`。
- Produces: `ReviewDecisionService.decide(task_id: str, decision: ReviewDecision, reason: str | None, principal: AuthenticatedPrincipal) -> ReviewDecisionResult`。

- [ ] **Step 1: Write the failing service tests**

覆盖批准后任务/调度/审计同时持久化、拒绝原因必填、不存在任务、非待复核任务、缺失调度和版本冲突。断言使用手工固定值，并重新打开数据库会话验证真实副作用。

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m pytest backend/tests/reviews/test_service.py -q`

Expected: collection fails because `app.reviews.service` does not exist.

- [ ] **Step 3: Write the minimal service**

定义 `ReviewDecision(APPROVE, REJECT)`、不可变结果模型和稳定领域异常。服务使用 `select(...).with_for_update()` 查任务，校验 `REVIEW_REQUIRED`，取得最新调度，设置任务/调度为 `APPROVED` 或 `REJECTED`，设置 `completed_at`，追加包含复核人证据的 `AuditRecord`，提交时捕获 `StaleDataError` 并抛出领域冲突。

- [ ] **Step 4: Run tests to verify GREEN**

Run: `python -m pytest backend/tests/reviews/test_service.py -q`

Expected: all service tests pass.

### Task 2: 权限受控的复核 API

**Files:**
- Create: `backend/app/api/v1/review_decisions.py`
- Create: `backend/app/api/v1/review_decision_schemas.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/security_support.py`
- Test: `backend/tests/api/test_review_decisions.py`
- Test: `backend/tests/api/test_endpoint_permissions.py`

**Interfaces:**
- Consumes: Task 1 `ReviewDecisionService.decide`。
- Produces: `POST /api/v1/reviews/{task_id}/decision`，请求 `decision` 与 `reason`，响应 `task_id`, `decision`, `status`, `reviewer`, `decided_at`, `dispatch_version`。

- [ ] **Step 1: Write failing API and permission tests**

验证主管/管理员成功、调度员 403、伪造 reviewer 字段 422、拒绝空原因 422、404/409 稳定错误码及服务收到认证主体。

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m pytest backend/tests/api/test_review_decisions.py backend/tests/api/test_endpoint_permissions.py -q`

Expected: 404 or import failure because the decision router is absent.

- [ ] **Step 3: Implement schemas, route and app wiring**

Pydantic 请求使用 `extra='forbid'`；路由依赖 `Permission.DISPATCH_REVIEW`，把领域异常映射为 `REVIEW_NOT_FOUND`、`REVIEW_ALREADY_DECIDED`、`REVIEW_DISPATCH_MISSING` 和 `DISPATCH_VERSION_CONFLICT`。`create_app` 支持注入测试服务，默认使用生产 session factory。

- [ ] **Step 4: Run tests to verify GREEN**

Run: `python -m pytest backend/tests/api/test_review_decisions.py backend/tests/api/test_endpoint_permissions.py -q`

Expected: all selected tests pass.

### Task 3: 前端 API 客户端与复核交互

**Files:**
- Create: `frontend/src/services/api/review-decision-client.ts`
- Create: `frontend/src/components/workspace/review-decision-dialog.tsx`
- Modify: `frontend/src/pages/reviews-page.tsx`
- Modify: `frontend/src/styles/components.css`
- Test: `frontend/tests/reviews-page.test.tsx`
- Test: `frontend/tests/review-decision-client.test.ts`

**Interfaces:**
- Consumes: Task 2 HTTP 契约和现有 `useReviewsRead().refresh`。
- Produces: `reviewDecisionApi.decide(taskId, payload)`；批准/拒绝对话框及成功刷新。

- [ ] **Step 1: Write failing frontend tests**

真实渲染页面并验证操作按钮；批准需二次确认，拒绝原因少于 2 字不能提交，成功调用客户端并刷新列表，409 显示“已由其他人员处理”，403 显示权限提示。

- [ ] **Step 2: Run tests to verify RED**

Run: `npm test -- --run tests/reviews-page.test.tsx tests/review-decision-client.test.ts`

Expected: tests fail because the action column, dialog and client do not exist.

- [ ] **Step 3: Implement client, dialog and page integration**

对话框为模块级组件，局部保存表单和提交状态；页面同一时间只处理一条任务，成功关闭并调用 `read.refresh()`。客户端复用认证 HTTP client，把稳定错误码映射成中文，不缓存决定请求。

- [ ] **Step 4: Run tests to verify GREEN**

Run: `npm test -- --run tests/reviews-page.test.tsx tests/review-decision-client.test.ts`

Expected: selected frontend tests pass.

### Task 4: 回归与真实 Docker 验收

**Files:**
- Modify: `docs/verification/manual-review-decisions.md`

**Interfaces:**
- Consumes: Tasks 1–3 完整闭环。
- Produces: 可复查的命令结果和真实 MySQL 状态证明。

- [ ] **Step 1: Run static and full unit verification**

Run: `ruff check backend`; `python -m pytest`; `npm run lint`; `npm test -- --run`; `npm run build`.

Expected: commands exit 0; only pre-existing documented warnings may remain.

- [ ] **Step 2: Rebuild Docker and run real decision probes**

使用系统管理员演示会话分别批准和拒绝两个 `DEMO-TASK-*`，断言 HTTP 200、复核总数减少、重复提交 409、MySQL 中任务/调度/审计三者一致，并确认其他角色 403。

- [ ] **Step 3: Verify one-click startup and diff**

Run the non-interactive one-click startup verification, then `git -c safe.directory=<workspace> diff --check` and inspect `git diff` plus untracked implementation files.

- [ ] **Step 4: Record exact verification evidence**

在 `docs/verification/manual-review-decisions.md` 记录实际命令、退出码、测试数量和不含令牌的 Docker 验收结果。

