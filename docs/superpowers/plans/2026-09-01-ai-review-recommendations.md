# CountyFlow AI Review Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist honest 8-Agent analysis for every manual-review task, distinguish road routing from vehicle/tire/cargo actions, and publish approved action-only instructions to the assigned employee.

**Architecture:** Add a pure issue recommendation domain service and call it from the existing routing node without adding a ninth graph node. Persist a `REVIEW_REQUIRED` dispatch draft before audit, project its analysis through MySQL-backed read models, and allow publication records to carry either a verified route, an approved action, or both. Recover old blank review rows through the existing runtime-thread and checkpoint ports.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, LangGraph, Redis checkpoint store, MySQL/SQLite tests, React 19, TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-01-ai-review-recommendations-design.md`

## Global Constraints

- Preserve the existing eight-node graph order; do not add a ninth agent.
- MySQL remains the source of truth; review list queries must not read Redis.
- Routes are accepted only from the routing provider's available candidates.
- Non-road incidents must never synthesize a route identifier.
- Use SQLAlchemy `version_id_col` and preserve existing 409 conflict handling.
- API/worker boundaries remain asynchronous; handlers do not run the graph.
- The UI copy is “8-Agent 协同分析”, never “大模型生成”.
- Every production behavior begins with a failing behavior-level test.
- Because this is an unborn shared workspace, do not create commits or alter the user's staging; use `git diff --check` checkpoints instead.

---

### Task 1: Pure issue recommendation domain service

**Files:**
- Create: `backend/app/recommendations/__init__.py`
- Create: `backend/app/recommendations/models.py`
- Create: `backend/app/recommendations/service.py`
- Test: `backend/tests/unit/test_issue_recommendation_service.py`

**Interfaces:**
- Consumes: `anomaly_type: str`, `anomaly_description: str`, `vehicle_status: str | None`, `environment_risk: str | None`, `capacity_status: str | None`, `candidate_routes: Sequence[Mapping[str, object]]`, `recommended_route: str | None`.
- Produces: `IssueRecommendation(issue_category, issue_subtype, analysis_reason, recommended_action, recommended_route, analysis_mode)` and `IssueRecommendationService.recommend(...)`.

- [ ] **Step 1: Write table-driven failing tests for issue classification and safe recommendations**

```python
@pytest.mark.parametrize(
    ("anomaly_type", "description", "category", "subtype", "action_fragment"),
    [
        ("VEHICLE_BREAKDOWN", "右后轮爆胎", "VEHICLE_BREAKDOWN", "TIRE", "更换轮胎"),
        ("ROAD_BLOCKED", "前方塌方封路", "ROAD_BLOCKED", "LANDSLIDE", "等待调度"),
        ("WEATHER", "暴雨能见度低", "WEATHER", "HEAVY_RAIN", "暂缓通行"),
        ("CARGO", "冷链温度异常", "CARGO", "TEMPERATURE", "检查"),
        ("CAPACITY", "车辆超载", "CAPACITY", "OVERLOAD", "转运"),
        ("OTHER", "现场情况不明", "OTHER", "GENERAL", "联系调度员"),
    ],
)
def test_recommendation_maps_real_incident_to_non_empty_action(...):
    result = service.recommend(...)
    assert (result.issue_category, result.issue_subtype) == (category, subtype)
    assert action_fragment in result.recommended_action
    assert result.analysis_reason
    assert result.analysis_mode == "EIGHT_AGENT_RULE_ASSISTED"
```

- [ ] **Step 2: Run the new unit tests and verify RED**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/unit/test_issue_recommendation_service.py -q`

Expected: collection fails because `app.recommendations` does not exist.

- [ ] **Step 3: Implement the immutable result model and deterministic service**

```python
@dataclass(frozen=True)
class IssueRecommendation:
    issue_category: str
    issue_subtype: str
    analysis_reason: str
    recommended_action: str
    recommended_route: str | None
    analysis_mode: str = "EIGHT_AGENT_RULE_ASSISTED"

class IssueRecommendationService:
    def recommend(self, *, anomaly_type: str, anomaly_description: str, ... ) -> IssueRecommendation:
        category = self._normalize_category(anomaly_type, anomaly_description)
        subtype = self._identify_subtype(category, anomaly_description)
        route = self._verified_route(recommended_route, candidate_routes)
        action = self._action(category, subtype, route)
        return IssueRecommendation(category, subtype, self._reason(...), action, route)
```

The literal rules must cover the seven categories in the spec. `_verified_route` returns the ID only when a candidate with the same ID has `available is True`; it returns `None` for all vehicle/tire/cargo incidents.

- [ ] **Step 4: Run recommendation tests and verify GREEN**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/unit/test_issue_recommendation_service.py -q`

Expected: all cases pass.

- [ ] **Step 5: Inspect the phase diff**

Run: `git -c safe.directory="C:/Users/24090/OneDrive/Desktop/县域物流识别异常" diff --check`

---

### Task 2: Add recommendation output to the existing routing node

**Files:**
- Modify: `backend/app/graph/state.py`
- Modify: `backend/app/graph/dependencies.py`
- Modify: `backend/app/graph/builder.py`
- Modify: `backend/app/agents/routing.py`
- Test: `backend/tests/graph/test_routing_agent.py`
- Test: `backend/tests/graph/test_ai_core_final.py`

**Interfaces:**
- Consumes: `IssueRecommendationService.recommend(...)` from Task 1.
- Produces: Graph patch keys `identified_issue`, `issue_subtype`, `recommended_action`, `analysis_mode`, a verified `recommended_route`, and user-facing `decision_reason`.

- [ ] **Step 1: Write a failing routing-node test for a tire report**

```python
result = await routing_node(tire_state, routing_service, IssueRecommendationService())
assert result["identified_issue"] == "VEHICLE_BREAKDOWN"
assert result["issue_subtype"] == "TIRE"
assert "更换轮胎" in result["recommended_action"]
assert result["recommended_route"] is None
assert result["analysis_mode"] == "EIGHT_AGENT_RULE_ASSISTED"
```

- [ ] **Step 2: Run the focused graph test and verify RED**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/graph/test_routing_agent.py -q`

Expected: signature/output assertion fails because recommendation integration is absent.

- [ ] **Step 3: Inject the service and extend state without changing graph topology**

```python
@dataclass(frozen=True)
class GraphDependencies:
    issue_recommendation_service: IssueRecommendationService = field(default_factory=IssueRecommendationService)

async def routing_node(state, routing_service, recommendation_service):
    routing = await routing_service.route(...)
    recommendation = recommendation_service.recommend(
        anomaly_type=state["anomaly_type"],
        anomaly_description=state["anomaly_description"],
        vehicle_status=state.get("vehicle_status"),
        environment_risk=state.get("environment_risk"),
        capacity_status=state.get("capacity_state", {}).get("capacity_status"),
        candidate_routes=[route_candidate_to_state(item) for item in routing.candidate_routes],
        recommended_route=routing.recommended_route,
    )
```

Add the four new `NotRequired` keys to `DispatchGraphState`; keep `NODE_ORDER` byte-for-byte unchanged.

- [ ] **Step 4: Run routing and graph topology tests and verify GREEN**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/graph/test_routing_agent.py tests/graph/test_ai_core_final.py tests/graph_memory/test_topology.py -q`

- [ ] **Step 5: Inspect the phase diff**

Run: `git -c safe.directory="C:/Users/24090/OneDrive/Desktop/县域物流识别异常" diff --check`

---

### Task 3: Persist a manual-review dispatch draft and audit evidence

**Files:**
- Modify: `backend/app/models/dispatch.py`
- Modify: `backend/app/dispatch/models.py`
- Modify: `backend/app/dispatch/service.py`
- Modify: `backend/app/agents/dispatch.py`
- Modify: `backend/app/agents/audit.py`
- Modify: `backend/app/audit/service.py`
- Create: `backend/alembic/versions/20260901_12_ai_review_recommendations.py`
- Test: `backend/tests/unit/test_dispatch_service.py`
- Test: `backend/tests/unit/test_audit_service.py`
- Create: `backend/tests/migrations/test_ai_review_recommendations_migration.py`

**Interfaces:**
- Consumes: recommendation state from Task 2.
- Produces: one idempotent `Dispatch(status="REVIEW_REQUIRED")` with optional route and non-empty action/mode; one idempotent `AuditRecord` bound to its real `dispatch_id`.

- [ ] **Step 1: Write failing tests for persisted and idempotent review drafts**

```python
first = service.execute(..., requires_manual_review=True,
    recommended_action="立即安全停车并更换轮胎。",
    analysis_mode="EIGHT_AGENT_RULE_ASSISTED", issue_subtype="TIRE")
second = service.execute(...same task...)
assert first.dispatch_id == second.dispatch_id
assert first.status == "REVIEW_REQUIRED"
assert first.executed is False
assert first.target_route_id is None
assert persisted.recommended_action == "立即安全停车并更换轮胎。"
assert count_dispatches == 1
```

- [ ] **Step 2: Run dispatch tests and verify RED**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/unit/test_dispatch_service.py -q`

Expected: `execute` rejects the new arguments and returns no dispatch ID for manual review.

- [ ] **Step 3: Add columns and persist review drafts through the existing repository transaction**

```python
class Dispatch(...):
    recommended_action: Mapped[str | None] = mapped_column(Text)
    analysis_mode: Mapped[str | None] = mapped_column(String(32))
    issue_subtype: Mapped[str | None] = mapped_column(String(32))
```

`DispatchService.execute` must open the session before branching, load the task, return any existing task dispatch, and create either `REVIEW_REQUIRED`, `REROUTED`, or `KEPT_ROUTE`. The review branch keeps `target_route_id=None` when no verified route and returns `executed=False`.

- [ ] **Step 4: Write and run a failing audit evidence test**

```python
payload = json.loads(record.evidence_json)
assert payload["analysis_mode"] == "EIGHT_AGENT_RULE_ASSISTED"
assert payload["identified_issue"] == "VEHICLE_BREAKDOWN"
assert payload["issue_subtype"] == "TIRE"
assert payload["capacity_status"] == "UNAVAILABLE"
assert payload["memory_hit_count"] == 1
```

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/unit/test_audit_service.py -q`

- [ ] **Step 5: Extend bounded audit evidence and verify GREEN**

Pass the new keys from `audit_node`, and add only scalar normalized fields plus `len(memory_results[:10])` in `_graph_evidence`.

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/unit/test_dispatch_service.py tests/unit/test_audit_service.py -q`

- [ ] **Step 6: Add and test Alembic revision `20260901_12`**

```python
with op.batch_alter_table("dispatches") as batch:
    batch.add_column(sa.Column("recommended_action", sa.Text(), nullable=True))
    batch.add_column(sa.Column("analysis_mode", sa.String(length=32), nullable=True))
    batch.add_column(sa.Column("issue_subtype", sa.String(length=32), nullable=True))
with op.batch_alter_table("dispatch_publications") as batch:
    batch.alter_column("route_id", existing_type=sa.String(length=64), nullable=True)
    batch.alter_column("route_instruction", existing_type=sa.Text(), nullable=True)
    batch.add_column(sa.Column("action_instruction", sa.Text(), nullable=True))
```

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/migrations/test_ai_review_recommendations_migration.py -q`

- [ ] **Step 7: Inspect the phase diff**

Run: `git -c safe.directory="C:/Users/24090/OneDrive/Desktop/县域物流识别异常" diff --check`

---

### Task 4: Project AI fields into the review API and frontend table

**Files:**
- Modify: `backend/app/workspace_reads/models.py`
- Modify: `backend/app/workspace_reads/sqlalchemy_repository.py`
- Modify: `backend/app/api/v1/workspace_read_schemas.py`
- Modify: `backend/tests/workspace_reads/test_sqlalchemy_repository.py`
- Modify: `backend/tests/api/test_workspace_reads.py`
- Modify: `frontend/src/types/workspace-read-models.ts`
- Modify: `frontend/src/pages/reviews-page.tsx`
- Modify: `frontend/tests/reviews-page.test.tsx`

**Interfaces:**
- Consumes: persisted Dispatch AI fields from Task 3.
- Produces: `ai_analysis_reason`, `ai_recommended_action`, `ai_analysis_mode`, `issue_subtype` in `/workspace/reviews` and the review table.

- [ ] **Step 1: Write failing repository/API projection tests**

```python
assert page.items[0].ai_analysis_reason == "轮胎故障且司机当前不可继续执行。"
assert page.items[0].ai_recommended_action == "安全停车、设置警示并更换轮胎。"
assert page.items[0].ai_analysis_mode == "EIGHT_AGENT_RULE_ASSISTED"
assert page.items[0].issue_subtype == "TIRE"
```

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/workspace_reads/test_sqlalchemy_repository.py tests/api/test_workspace_reads.py -q`

Expected: model/schema fields do not exist.

- [ ] **Step 2: Extend the MySQL projection and response schema**

Select the latest Dispatch fields. Keep `reason` as a compatibility alias of `Dispatch.decision_reason`; never use the audit's generic “Dispatch requires manual review” as the primary AI reason.

- [ ] **Step 3: Verify backend projection GREEN**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/workspace_reads/test_sqlalchemy_repository.py tests/api/test_workspace_reads.py -q`

- [ ] **Step 4: Write the failing UI behavior test**

```typescript
expect(container.textContent).toContain("AI 分析原因");
expect(container.textContent).toContain("AI 处置建议");
expect(container.textContent).toContain("8-Agent 分析完成");
expect(container.textContent).toContain("当前不适用");
expect(container.textContent).toContain("安全停车、设置警示并更换轮胎");
```

Run: `cd frontend && npm test -- --run tests/reviews-page.test.tsx`

Expected: new labels/content are absent.

- [ ] **Step 5: Render honest AI fields and route-not-applicable copy**

```tsx
{ key: "ai_analysis_reason", label: "AI 分析原因" },
{ key: "ai_recommended_action", label: "AI 处置建议" },
{ key: "suggested_route_id", label: "建议路线", render: item => item.suggested_route_id ?? "当前不适用" },
{ key: "ai_analysis_mode", label: "AI 状态", render: item => item.ai_analysis_mode ? <StatusBadge status="COMPLETED" label="8-Agent 分析完成" /> : "待补全" },
```

- [ ] **Step 6: Run frontend focused tests and inspect diff**

Run: `cd frontend && npm test -- --run tests/reviews-page.test.tsx`

Run: `git -c safe.directory="C:/Users/24090/OneDrive/Desktop/县域物流识别异常" diff --check`

---

### Task 5: Approve and publish action-only instructions

**Files:**
- Modify: `backend/app/models/dispatch_publication.py`
- Modify: `backend/app/publications/service.py`
- Modify: `backend/app/workspace_reads/models.py`
- Modify: `backend/app/workspace_reads/sqlalchemy_repository.py`
- Modify: `backend/app/api/v1/workspace_read_schemas.py`
- Modify: `backend/tests/publications/test_service.py`
- Modify: `backend/tests/reviews/test_service.py`
- Modify: `frontend/src/types/workspace-read-models.ts`
- Modify: employee task page/component selected by existing My Tasks projection tests
- Modify: `frontend/tests/dispatcher-workspace.test.tsx`

**Interfaces:**
- Consumes: approved Dispatch with `target_route_id: str | None` and `recommended_action: str | None`.
- Produces: `DispatchPublication(route_id, route_instruction, action_instruction)` and employee `action_instruction` only after approval/publication.

- [ ] **Step 1: Write failing action-only publication tests**

```python
result = service.publish("task-001", supervisor)
assert result["route_id"] is None
assert result["route_instruction"] is None
assert result["action_instruction"] == "安全停车、设置警示并更换轮胎。"
```

Also assert publication is rejected with `PublicationInstructionMissing` when both route and action are absent.

- [ ] **Step 2: Run publication/review tests and verify RED**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/publications/test_service.py tests/reviews/test_service.py -q`

- [ ] **Step 3: Implement route-or-action publication without weakening approval checks**

```python
route_id = dispatch.target_route_id
action = dispatch.recommended_action
if route_id is None and action is None:
    raise PublicationInstructionMissing
publication = DispatchPublication(
    route_id=route_id,
    route_instruction=self._route_instruction(order, route_id) if route_id else None,
    action_instruction=action,
    ...,
)
```

Do not fall back to `original_route_id` for a non-road incident. Preserve idempotency and authorization.

- [ ] **Step 4: Expose approved action instructions to the employee projection**

Add `action_instruction: str | None` to `MyTaskListItem`, response schema, TypeScript type, and employee task rendering. The projection remains `NULL` until a `dispatch_publications` row exists.

- [ ] **Step 5: Run backend and frontend focused tests and inspect diff**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/publications/test_service.py tests/reviews/test_service.py tests/workspace_reads/test_sqlalchemy_repository.py -q`

Run: `cd frontend && npm test -- --run tests/dispatcher-workspace.test.tsx tests/supervisor-workspace.test.tsx`

Run: `git -c safe.directory="C:/Users/24090/OneDrive/Desktop/县域物流识别异常" diff --check`

---

### Task 6: Recover terminal blank review tasks through narrow ports

**Files:**
- Create: `backend/app/recovery/__init__.py`
- Create: `backend/app/recovery/review_proposals.py`
- Create: `backend/app/cli/recover_review_proposals.py`
- Create: `backend/tests/recovery/test_review_proposals.py`

**Interfaces:**
- Consumes: `RuntimeThreadRepository.get_by_task_id`, `RuntimeCheckpointStore.get_exact`, `IssueRecommendationService`, `DispatchService`, `AuditService`.
- Produces: `RecoveryReport(recovered_task_ids, skipped_task_ids, unchanged_task_ids)`; repeated runs are idempotent.

- [ ] **Step 1: Write failing recovery tests with real SQLite domain rows and a narrow checkpoint fake**

```python
report = await service.recover()
assert report.recovered_task_ids == ("TASK-old-review",)
assert persisted_dispatch.issue_subtype == "TIRE"
assert persisted_dispatch.target_route_id is None
assert persisted_audit.dispatch_id == persisted_dispatch.id
assert (await service.recover()).unchanged_task_ids == ("TASK-old-review",)
```

Add a missing-checkpoint case that is reported in `skipped_task_ids` and creates no guessed data.

- [ ] **Step 2: Run recovery tests and verify RED**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/recovery/test_review_proposals.py -q`

- [ ] **Step 3: Implement recovery orchestration without importing Redis**

The service queries only `REVIEW_REQUIRED` tasks lacking Dispatch, obtains the runtime snapshot through the repository protocol, reads exactly `current_checkpoint_id` through the checkpoint protocol, derives the recommendation, executes Dispatch, then Audit. The CLI only builds configured adapters and prints counts plus skipped task IDs; it never logs checkpoint bodies.

- [ ] **Step 4: Run recovery tests and inspect diff**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/recovery/test_review_proposals.py -q`

Run: `git -c safe.directory="C:/Users/24090/OneDrive/Desktop/县域物流识别异常" diff --check`

---

### Task 7: Full verification, migration, recovery, and live E2E

**Files:**
- Modify only if a failing verification exposes a covered regression.

**Interfaces:**
- Consumes: Tasks 1–6.
- Produces: migrated live services, repaired existing review rows, and evidence for road and tire workflows.

- [ ] **Step 1: Run backend static and unit/integration verification**

Run: `cd backend && .venv/Scripts/python.exe -m ruff check app tests`

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`

- [ ] **Step 2: Run frontend verification**

Run: `cd frontend && npm run lint`

Run: `cd frontend && npm test -- --run`

Run: `cd frontend && npm run build`

- [ ] **Step 3: Apply migration and rebuild the Docker services**

Run the repository's existing Docker Compose migration/start workflow; verify backend health and worker consumer readiness before submitting tasks.

- [ ] **Step 4: Execute the recovery CLI once**

Record recovered/skipped/unchanged counts. Re-run it and verify the second run creates no extra Dispatch or Audit rows.

- [ ] **Step 5: Exercise two live employee reports**

1. Submit a road blockage and verify the supervisor sees a real route only if a provider candidate exists.
2. Submit “右后轮爆胎，车辆无法继续行驶” and verify the supervisor sees subtype `TIRE`, a tire/rescue action, “当前不适用” for route, and “8-Agent 分析完成”.
3. Approve the tire task, publish it, and verify only the assigned employee sees the action instruction.

- [ ] **Step 6: Run final repository checks**

Run: `git -c safe.directory="C:/Users/24090/OneDrive/Desktop/县域物流识别异常" diff --check`

Run: `git -c safe.directory="C:/Users/24090/OneDrive/Desktop/县域物流识别异常" diff --stat`

Record only actual output; do not claim runtime services were tested unless the Docker E2E completed.
