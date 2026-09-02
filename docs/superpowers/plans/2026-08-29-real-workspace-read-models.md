# CountyFlow Real Workspace Read Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the API-mode placeholder surfaces with bounded, permission-protected MySQL/Qdrant read models and clearly marked non-production business seed data.

**Architecture:** A focused `workspace_reads` application module exposes safe domain DTOs through a service that depends on separate MySQL and Qdrant protocols. FastAPI routes perform permission admission and response validation; React uses one typed client and explicit loading/ready/empty/forbidden/unavailable states without Mock fallback.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Qdrant Client, Pydantic 2, pytest, React, TypeScript, Vitest, Playwright, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-29-real-workspace-read-models-design.md`

## Global Constraints

- API handlers validate, authorize, call narrow services, and return typed safe responses; they do not query SQLAlchemy or Qdrant directly.
- MySQL remains the source of truth for orders, anomalies, tasks, dispatches, audits, and runtime metadata; Qdrant remains the vector-memory source.
- Every list defaults to 20 records, accepts 1–100, and uses a stable cursor.
- API mode never imports or calls frontend Mock services.
- Raw vectors, raw runtime checkpoints, credentials, authorization headers, and connection URLs never enter a response or log.
- Development business seeds run only for `local`, `test`, and `docker-dev`; production skips them.
- Development seeds may create orders, anomalies, and vector memories, but never fabricate terminal tasks, dispatches, audits, or runtime threads.
- Existing RBAC permissions remain the endpoint boundary; `system:admin` is not a wildcard.
- Do not weaken existing tests or increase timing thresholds to make failures pass.
- Git identity is currently absent. Never invent or change `user.name`/`user.email`; if a commit command is blocked, record the blocker and continue with the working tree intact.

## File Structure

- `backend/app/workspace_reads/models.py`: immutable read-model DTOs and page containers.
- `backend/app/workspace_reads/protocols.py`: narrow MySQL and vector-memory read protocols.
- `backend/app/workspace_reads/sqlalchemy_repository.py`: bounded joins and summary queries over MySQL.
- `backend/app/workspace_reads/qdrant_repository.py`: safe Qdrant scroll and collection metadata.
- `backend/app/workspace_reads/service.py`: composition, cursor validation, and source semantics.
- `backend/app/api/v1/workspace_read_schemas.py`: Pydantic response contracts.
- `backend/app/api/v1/workspace_reads.py`: six permission-protected GET routes.
- `backend/app/seed.py`: idempotent non-production orders/anomalies/vector-memory seeds.
- `frontend/src/types/workspace-read-models.ts`: API response and UI state types.
- `frontend/src/services/api/workspace-read-client.ts`: authenticated typed requests.
- `frontend/src/hooks/use-workspace-reads.ts`: shared request state and filter-driven hooks.
- `frontend/src/pages/reviews-page.tsx`: real read-only review queue.
- `frontend/src/pages/runtime-page.tsx`: real global runtime-thread list.
- Existing overview, anomalies, orders, memory, operations, router, and tests: wire the new contracts.

---

### Task 1: MySQL Workspace Read Repository

**Files:**
- Create: `backend/app/workspace_reads/__init__.py`
- Create: `backend/app/workspace_reads/models.py`
- Create: `backend/app/workspace_reads/protocols.py`
- Create: `backend/app/workspace_reads/sqlalchemy_repository.py`
- Test: `backend/tests/workspace_reads/test_sqlalchemy_repository.py`

**Interfaces:**
- Consumes: existing SQLAlchemy models `Order`, `Anomaly`, `DispatchTask`, `Dispatch`, `AuditRecord`, and `RuntimeThread`.
- Produces: `SqlAlchemyWorkspaceReadRepository.list_orders`, `.list_anomalies`, `.list_reviews`, `.list_runtime_threads`, and `.count_domains` returning immutable read DTOs.

- [ ] **Step 1: Write failing repository tests with literal expected projections**

```python
def test_list_reviews_returns_only_review_required_with_safe_joined_fields(sqlite_factory):
    seed_review_and_approved_tasks(sqlite_factory)
    repository = SqlAlchemyWorkspaceReadRepository(sqlite_factory)

    page = repository.list_reviews(limit=20, before_id=None)

    assert page.total == 1
    assert page.items == (
        ReviewListItem(
            row_id=2,
            task_id="TASK-review-2",
            order_no="DEMO-ORDER-002",
            risk="HIGH",
            reason="道路封闭",
            vehicle_id="苏G·N2148",
            original_route_id="东河乡道",
            suggested_route_id=None,
            status="REVIEW_REQUIRED",
            created_at=REVIEW_TIME,
        ),
    )
```

Add independent tests for order/anomaly filters, deterministic `before_id`, runtime safe fields, exact totals, and absence of checkpoint payload attributes.

- [ ] **Step 2: Run the repository tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests/workspace_reads/test_sqlalchemy_repository.py -q`

Expected: collection/import failure because `app.workspace_reads` does not exist.

- [ ] **Step 3: Define immutable models and narrow protocol**

```python
@dataclass(frozen=True)
class Page(Generic[T]):
    items: tuple[T, ...]
    total: int
    next_cursor: str | None
    provenance: Literal["LIVE", "DEMO", "MIXED"]

class WorkspaceReadRepository(Protocol):
    def list_orders(self, *, limit: int, before_id: int | None, query: str | None, status: str | None) -> Page[OrderListItem]: ...
    def list_anomalies(self, *, limit: int, before_id: int | None, query: str | None, risk: str | None, status: str | None) -> Page[AnomalyListItem]: ...
    def list_reviews(self, *, limit: int, before_id: int | None) -> Page[ReviewListItem]: ...
    def list_runtime_threads(self, *, limit: int, before_id: int | None, status: str | None) -> Page[RuntimeThreadListItem]: ...
    def count_domains(self) -> DomainCounts: ...
```

- [ ] **Step 4: Implement bounded SQLAlchemy queries**

Use explicit selected columns and outer joins. Order each query by the owning table ID descending, apply `id < before_id`, fetch `limit + 1`, and derive the next cursor from the last returned row only when another row exists. Count queries apply the same filters but never load ORM entity graphs.

```python
rows = session.execute(statement.order_by(DispatchTask.id.desc()).limit(limit + 1)).all()
visible = rows[:limit]
next_cursor = str(visible[-1].id) if len(rows) > limit else None
```

- [ ] **Step 5: Run focused and adjacent repository tests**

Run: `..\.venv\Scripts\python.exe -m pytest tests/workspace_reads/test_sqlalchemy_repository.py tests/runtime_threads tests/unit/test_api_conflict.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the independently working MySQL read repository**

```powershell
git add backend/app/workspace_reads backend/tests/workspace_reads/test_sqlalchemy_repository.py
git commit -m "feat: add workspace mysql read models"
```

If Git reports missing identity, do not configure it; record the blocked commit and continue.

---

### Task 2: Qdrant Vector Memory Browser

**Files:**
- Create: `backend/app/workspace_reads/qdrant_repository.py`
- Modify: `backend/app/workspace_reads/models.py`
- Modify: `backend/app/workspace_reads/protocols.py`
- Test: `backend/tests/workspace_reads/test_qdrant_repository.py`

**Interfaces:**
- Consumes: Qdrant collection `entity_resolution_memory` and payload fields written by `QdrantMemoryRepository.upsert`.
- Produces: `QdrantVectorMemoryReadRepository.list_records(limit, cursor)` returning `VectorMemoryPage` with actual collection dimension and no vectors.

- [ ] **Step 1: Write a failing in-memory Qdrant behavior test**

```python
@pytest.mark.asyncio
async def test_vector_memory_page_uses_actual_dimension_and_omits_vectors():
    client = QdrantClient(":memory:")
    write_two_memories(client, dimension=128)
    repository = QdrantVectorMemoryReadRepository(client, "entity_resolution_memory")

    page = await repository.list_records(limit=1, cursor=None)

    assert page.vector_dimension == 128
    assert page.items[0].memory_id == "memory-rain-li"
    assert not hasattr(page.items[0], "vector")
    assert page.next_cursor is not None
```

Add tests for the second page, missing collection as a valid empty page, malformed cursor, and Qdrant transport error normalization.

- [ ] **Step 2: Run and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests/workspace_reads/test_qdrant_repository.py -q`

Expected: import failure for `QdrantVectorMemoryReadRepository`.

- [ ] **Step 3: Implement scroll with payload-only projection**

```python
points, next_offset = await asyncio.to_thread(
    self._client.scroll,
    collection_name=self._collection,
    limit=limit,
    offset=decoded_cursor,
    with_payload=True,
    with_vectors=False,
)
collection = await asyncio.to_thread(self._client.get_collection, self._collection)
```

Validate payload keys individually, replace absent optional values with `None`, derive dimension from collection configuration, and convert Qdrant failures to `VectorMemoryReadUnavailable` without embedding URLs or request details.

- [ ] **Step 4: Run Qdrant and existing memory tests**

Run: `..\.venv\Scripts\python.exe -m pytest tests/workspace_reads/test_qdrant_repository.py tests/memory tests/shared_memory/test_qdrant_projection.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the vector read boundary**

```powershell
git add backend/app/workspace_reads backend/tests/workspace_reads/test_qdrant_repository.py
git commit -m "feat: add safe vector memory browser"
```

---

### Task 3: Workspace Service, API Contracts, Permissions, and App Wiring

**Files:**
- Create: `backend/app/workspace_reads/service.py`
- Create: `backend/app/api/v1/workspace_read_schemas.py`
- Create: `backend/app/api/v1/workspace_reads.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/api/test_endpoint_permissions.py`
- Test: `backend/tests/api/test_workspace_reads.py`

**Interfaces:**
- Consumes: `WorkspaceReadRepository` and `VectorMemoryReadRepository`.
- Produces: `WorkspaceReadService` methods and six endpoints defined by the approved spec.

- [ ] **Step 1: Write failing API contract tests**

```python
def test_review_list_requires_dispatch_review_permission():
    service = StubWorkspaceReadService()
    app = create_app(workspace_read_service=service, **auth(Role.DISPATCHER))
    response = TestClient(app).get("/api/v1/reviews", headers=headers())
    assert response.status_code == 403
    assert service.review_calls == 0

def test_runtime_list_never_serializes_checkpoint_payload():
    app = create_app(workspace_read_service=ready_service(), **auth(Role.OPERATOR))
    body = TestClient(app).get("/api/v1/runtime/threads", headers=headers()).json()
    assert body["items"][0]["task_id"] == "TASK-1"
    assert "checkpoint" not in body["items"][0]
    assert "state" not in body["items"][0]
```

Add one success test per route, 422 tests for `limit=0`, `limit=101`, and malformed cursor, a 503 vector-memory test, a 200 empty-page test, and role-denial tests for all six permissions.

- [ ] **Step 2: Run and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests/api/test_workspace_reads.py tests/api/test_endpoint_permissions.py -q`

Expected: `create_app` rejects `workspace_read_service` and routes return 404.

- [ ] **Step 3: Implement service validation and Pydantic schemas**

```python
class WorkspaceReadService:
    def list_reviews(self, *, limit: int, cursor: str | None) -> Page[ReviewListItem]:
        return self._mysql.list_reviews(limit=limit, before_id=parse_numeric_cursor(cursor))

    async def list_vector_memories(self, *, limit: int, cursor: str | None) -> VectorMemoryPage:
        return await self._vectors.list_records(limit=limit, cursor=cursor)
```

Pydantic response models use `extra="forbid"`, serialize timestamps as ISO 8601, and expose the exact safe fields in the spec.

- [ ] **Step 4: Add permission-protected routes**

```python
@router.get("/reviews", response_model=ReviewPageResponse)
def list_reviews(
    service: ServiceDependency,
    _principal: Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.DISPATCH_REVIEW))],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> ReviewPageResponse:
    return ReviewPageResponse.model_validate(service.list_reviews(limit=limit, cursor=cursor), from_attributes=True)
```

Implement all six exact paths and normalize only repository availability errors to 503 codes `WORKSPACE_READ_UNAVAILABLE` or `VECTOR_MEMORY_UNAVAILABLE`.

- [ ] **Step 5: Wire one shared service in `create_app`**

Add optional injection `workspace_read_service: WorkspaceReadService | None = None`. When absent, create one SQLAlchemy repository from the existing session factory and one Qdrant repository from a dedicated client. Register the router and close the dedicated Qdrant client on shutdown.

- [ ] **Step 6: Run API, permission, OpenAPI, and security tests**

Run: `..\.venv\Scripts\python.exe -m pytest tests/api/test_workspace_reads.py tests/api/test_endpoint_permissions.py tests/api/test_dispatch_api_e2e.py tests/security -q`

Expected: PASS and no unauthorized stub call.

- [ ] **Step 7: Commit the API boundary**

```powershell
git add backend/app/api/v1/workspace_reads.py backend/app/api/v1/workspace_read_schemas.py backend/app/workspace_reads/service.py backend/app/main.py backend/tests/api
git commit -m "feat: expose permission scoped workspace reads"
```

---

### Task 4: Idempotent Non-Production Business Seeds

**Files:**
- Modify: `backend/app/seed.py`
- Test: `backend/tests/unit/test_seed.py`

**Interfaces:**
- Consumes: `runtime_profile`, existing session factory, `Order`, `Anomaly`, and `EntityMemoryService`.
- Produces: `seed_database(session_factory=None, runtime_profile=None)` with ten stable demo business cases and production skip behavior.

- [ ] **Step 1: Write failing seed behavior tests**

```python
def test_development_seed_is_idempotent_and_diverse(sqlite_factory):
    seed_database(session_factory=sqlite_factory, runtime_profile="docker-dev")
    seed_database(session_factory=sqlite_factory, runtime_profile="docker-dev")
    with sqlite_factory() as session:
        orders = session.scalars(select(Order).where(Order.order_no.like("DEMO-ORDER-%"))).all()
        anomalies = session.scalars(select(Anomaly).where(Anomaly.anomaly_no.like("DEMO-ANOM-%"))).all()
        tasks = session.scalars(select(DispatchTask).where(DispatchTask.idempotency_key.like("demo-seed-%"))).all()
    assert len(orders) == 10
    assert len(anomalies) == 10
    assert {row.severity for row in anomalies} == {"HIGH", "MEDIUM", "LOW"}
    assert tasks == []

def test_production_seed_does_not_create_demo_business_rows(sqlite_factory):
    seed_database(session_factory=sqlite_factory, runtime_profile="production")
    with sqlite_factory() as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 0
```

- [ ] **Step 2: Run and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests/unit/test_seed.py -q`

Expected: `seed_database` does not accept injected arguments and only one legacy case exists.

- [ ] **Step 3: Implement stable Chinese business cases**

Define ten immutable case dictionaries with literal order/anomaly numbers and fields. Query by unique number before insert, flush the order before constructing its anomaly, and commit once. Gate demo cases with:

```python
profile = runtime_profile or get_settings().runtime_profile
if profile in {"local", "test", "docker-dev"}:
    seed_demo_business_cases(session)
```

Keep the existing canonical rain memory, but derive its Qdrant dimension and fake provider model from the active development settings instead of page copy.

- [ ] **Step 4: Run seed and model tests**

Run: `..\.venv\Scripts\python.exe -m pytest tests/unit/test_seed.py tests/graph_memory/test_seed.py tests/memory -q`

Expected: PASS.

- [ ] **Step 5: Commit the non-production seed**

```powershell
git add backend/app/seed.py backend/tests/unit/test_seed.py
git commit -m "feat: seed marked development business cases"
```

---

### Task 5: Typed Frontend Client and Read Hooks

**Files:**
- Create: `frontend/src/types/workspace-read-models.ts`
- Modify: `frontend/src/services/api/workspace-read-client.ts`
- Create: `frontend/src/hooks/use-workspace-reads.ts`
- Modify: `frontend/tests/workspace-read-client.test.ts`
- Create: `frontend/tests/workspace-read-hooks.test.tsx`

**Interfaces:**
- Consumes: existing authenticated `ApiClient.request<T>()` and six JSON contracts.
- Produces: `workspaceReadClient` and hooks `useOverview`, `useOrdersRead`, `useAnomaliesRead`, `useReviewsRead`, `useRuntimeThreadsRead`, `useVectorMemoriesRead`.

- [ ] **Step 1: Replace the obsolete client expectation with failing real-request tests**

```typescript
it("requests the bounded anomaly list without using Mock data", async () => {
  const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(anomalyPage));
  const client = createWorkspaceReadClient({ baseUrl: "http://api.test", fetchImpl });
  await expect(client.getAnomalies({ limit: 20, risk: "HIGH" })).resolves.toEqual(anomalyPage);
  expect(fetchImpl).toHaveBeenCalledWith(
    "http://api.test/api/v1/anomalies?limit=20&risk=HIGH",
    expect.objectContaining({ credentials: "same-origin" }),
  );
});
```

Add one literal contract fixture per endpoint and assert no import from `mocks/workspace-data`.

- [ ] **Step 2: Run client tests and verify RED**

Run: `npm test -- workspace-read-client.test.ts`

Expected: missing `getAnomalies`, `getOrders`, `getReviews`, `getRuntimeThreads`, `getVectorMemories`, and `getOverview` methods.

- [ ] **Step 3: Define API types and implement client methods**

```typescript
export interface PageResponse<T> {
  items: T[];
  total: number;
  next_cursor: string | null;
  provenance: "LIVE" | "DEMO" | "MIXED";
}

async getAnomalies(filters: AnomalyFilters) {
  return requestPage<AnomalyListItem>("/api/v1/anomalies", filters);
}
```

Use `URLSearchParams`, omit empty filters, and preserve cursor strings without parsing them in the browser.

- [ ] **Step 4: Write failing hook state-transition tests**

```typescript
it("moves from loading to ready and keeps API provenance", async () => {
  const { result } = renderHook(() => useOrdersRead({ query: "李师傅" }), { wrapper });
  expect(result.current.state).toBe("LOADING");
  await waitFor(() => expect(result.current.state).toBe("READY"));
  expect(result.current.data?.provenance).toBe("LIVE");
});
```

Cover 403→`FORBIDDEN`, 503→`UNAVAILABLE`, other errors→`ERROR`, empty items→`EMPTY`, stale request cancellation, and filter refresh.

- [ ] **Step 5: Implement the hooks with one shared request-state helper**

The helper accepts a promise factory and dependency list, aborts stale requests, and never imports Mock services. Return the existing `ReadState<T>` vocabulary.

- [ ] **Step 6: Run client and hook tests**

Run: `npm test -- workspace-read-client.test.ts workspace-read-hooks.test.tsx runtime-config.test.ts`

Expected: PASS.

- [ ] **Step 7: Commit the frontend data boundary**

```powershell
git add frontend/src/types/workspace-read-models.ts frontend/src/services/api/workspace-read-client.ts frontend/src/hooks/use-workspace-reads.ts frontend/tests
git commit -m "feat: connect typed workspace read client"
```

---

### Task 6: Overview, Anomalies, and Orders Live Pages

**Files:**
- Modify: `frontend/src/pages/admin-overview-page.tsx`
- Modify: `frontend/src/pages/anomalies-page.tsx`
- Modify: `frontend/src/pages/orders-page.tsx`
- Modify: `frontend/tests/admin-workspace.test.tsx`
- Modify: `frontend/tests/business-pages-data-truth.test.tsx`

**Interfaces:**
- Consumes: `useOverview`, `useAnomaliesRead`, `useOrdersRead`.
- Produces: three API-mode pages with real metrics, filters, tables, pagination, drawers, and explicit provenance.

- [ ] **Step 1: Write failing rendered behavior tests**

```typescript
it("renders live anomaly rows and removes the not-exposed message", async () => {
  server.use(anomalyPageHandler({ total: 10, high_risk: 3 }));
  const container = await render(<AnomaliesPage />);
  await screen.findByText("DEMO-ANOM-001");
  expect(container.textContent).toContain("当前异常10");
  expect(container.textContent).toContain("高风险3");
  expect(container.textContent).not.toContain("异常列表接口尚未开放");
});
```

Add tests for order rows, source badge, empty 200 state, unavailable retry, filter query, next-page button, and overview domain statuses.

- [ ] **Step 2: Run and verify RED**

Run: `npm test -- business-pages-data-truth.test.tsx admin-workspace.test.tsx`

Expected: pages still render `NOT_EXPOSED` and never call the client.

- [ ] **Step 3: Implement API-mode page state branches**

Keep existing Mock-mode rendering unchanged. In API mode, render skeletons for loading, the shared authorization/unavailable states for failures, business empty copy for zero rows, and current data for ready state. Metrics come exclusively from response summary fields.

```tsx
if (read.state === "READY") {
  return <BusinessTable items={read.data.items} provenance={read.data.provenance} />;
}
return <WorkspaceReadState state={read.state} onRetry={read.retry} />;
```

- [ ] **Step 4: Run the focused page tests**

Run: `npm test -- business-pages-data-truth.test.tsx admin-workspace.test.tsx workspace-ui.test.tsx`

Expected: PASS.

- [ ] **Step 5: Commit the business pages**

```powershell
git add frontend/src/pages/admin-overview-page.tsx frontend/src/pages/anomalies-page.tsx frontend/src/pages/orders-page.tsx frontend/tests
git commit -m "feat: render live business workspace data"
```

---

### Task 7: Reviews, Runtime, and Operations Pages

**Files:**
- Create: `frontend/src/pages/reviews-page.tsx`
- Create: `frontend/src/pages/runtime-page.tsx`
- Modify: `frontend/src/pages/supervisor-workspace-page.tsx`
- Modify: `frontend/src/pages/operations-page.tsx`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/tests/supervisor-workspace.test.tsx`
- Modify: `frontend/tests/operator-workspace.test.tsx`
- Modify: `frontend/tests/role-routes.test.tsx`
- Create: `frontend/tests/runtime-list.test.tsx`

**Interfaces:**
- Consumes: `useReviewsRead` and `useRuntimeThreadsRead`.
- Produces: `/reviews` and `/runtime` real list pages plus live supervisor/operations summaries.

- [ ] **Step 1: Write failing route and rendering tests**

```typescript
it("renders the real read-only review queue without review actions", async () => {
  renderSupervisorWithApi(reviewPage);
  await screen.findByText("TASK-review-2");
  expect(screen.getByText("等待人工复核")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /批准|拒绝/ })).toBeNull();
});

it("renders safe runtime metadata and no checkpoint payload", async () => {
  renderRuntimeWithApi(runtimePage);
  await screen.findByText("cf:dispatch:TASK-1");
  expect(screen.getByText("V7")).toBeInTheDocument();
  expect(document.body.textContent).not.toContain("checkpoint_payload");
});
```

- [ ] **Step 2: Run and verify RED**

Run: `npm test -- supervisor-workspace.test.tsx operator-workspace.test.tsx role-routes.test.tsx runtime-list.test.tsx`

Expected: `/reviews` and `/runtime` still resolve to `NotExposedPage`.

- [ ] **Step 3: Implement the two pages and route replacements**

The review page uses `ReviewQueue` with API rows and a link to `/dispatch/{taskId}` only. The runtime page uses `DataTable` with status, current/next node, version, update time, and task link. It never offers override actions globally.

- [ ] **Step 4: Reuse live counts in role workspaces**

Supervisor metrics use review totals and runtime status counts. Operations replaces the global runtime placeholder with a bounded first-page summary and links to the full runtime page; its observability panel remains independent.

- [ ] **Step 5: Run focused role and accessibility tests**

Run: `npm test -- supervisor-workspace.test.tsx operator-workspace.test.tsx role-routes.test.tsx runtime-list.test.tsx responsive-accessibility.test.ts`

Expected: PASS.

- [ ] **Step 6: Commit the review and runtime surfaces**

```powershell
git add frontend/src/pages frontend/src/app/router.tsx frontend/tests
git commit -m "feat: add live review and runtime lists"
```

---

### Task 8: Live Vector Memory Page

**Files:**
- Modify: `frontend/src/pages/memory-page.tsx`
- Modify: `frontend/tests/memory-control-plane.test.tsx`
- Modify: `frontend/tests/v2-data-contracts.test.ts`
- Create: `frontend/tests/vector-memory-list.test.tsx`

**Interfaces:**
- Consumes: `useVectorMemoriesRead`.
- Produces: API-mode vector-memory metrics and list using current Qdrant metadata.

- [ ] **Step 1: Write a failing 128-dimension rendered test**

```typescript
it("shows the current Qdrant dimension and records instead of fixed acceptance evidence", async () => {
  renderMemoryWithApi(vectorPage({ vector_dimension: 128, provider: "开发嵌入", model: "development-deterministic-128" }));
  await screen.findByText("memory-rain-li");
  expect(screen.getByText("128")).toBeInTheDocument();
  expect(document.body.textContent).not.toContain("2560");
  expect(document.body.textContent).not.toContain("当前后端未暴露向量记忆浏览 API");
});
```

Add tests for empty collection, 503 unavailable state, filter input, pagination, source badge, and absence of vector values.

- [ ] **Step 2: Run and verify RED**

Run: `npm test -- vector-memory-list.test.tsx memory-control-plane.test.tsx v2-data-contracts.test.ts`

Expected: fixed 2560/SiliconFlow evidence remains and no API list appears.

- [ ] **Step 3: Implement live metadata and rows**

Retain Graph and Shared Control tabs. For Vector Memory in API mode, derive every metric from the response and render actual payload fields. Use a neutral localized label for the fake development provider and preserve branded provider names only when the server supplies an approved safe label.

- [ ] **Step 4: Run memory and localization tests**

Run: `npm test -- vector-memory-list.test.tsx memory-control-plane.test.tsx localized-business-copy.test.tsx graph-monitoring-light.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit the memory page**

```powershell
git add frontend/src/pages/memory-page.tsx frontend/tests
git commit -m "feat: browse live vector memory records"
```

---

### Task 9: Docker Integration, Browser QA, and Final Verification

**Files:**
- Modify only if a verification failure identifies a root cause in an already planned file.
- Temporary Playwright scripts/screenshots: create outside the repository.

**Interfaces:**
- Consumes: all tasks above and the exact `http://localhost:5173` Docker frontend.
- Produces: verified one-click runtime with populated pages and recorded command evidence.

- [ ] **Step 1: Run static and unit verification**

```powershell
.\.venv\Scripts\python.exe -m ruff check backend
Push-Location backend
$env:DEVELOPMENT_JWT_SECRET='test-only-signing-material-32-chars'
..\.venv\Scripts\python.exe -m pytest -q --basetemp .codex-workspace-read-tests
Pop-Location
Push-Location frontend
npm run lint
npm test
npm run build
Pop-Location
```

Expected: Ruff pass; backend and frontend tests pass; frontend production build succeeds. Remove only the explicitly created `.codex-workspace-read-tests` after resolving it inside the workspace.

- [ ] **Step 2: Rebuild and start through the exact one-click entry**

Run: `cmd.exe /c "一键启动完整版.bat"`

Expected: exit code 0, 11/11 Compose services ready, and no batch parsing errors.

- [ ] **Step 3: Verify real source counts and contracts**

Check MySQL demo order/anomaly counts, Qdrant collection dimension and records, and authenticated HTTP responses for all six new routes. Assert that `/api/v1/memory/records` contains no `vector` key and `/api/v1/runtime/threads` contains no checkpoint payload key.

- [ ] **Step 4: Run Playwright rendered QA because the Browser plugin is absent**

The flow under test is: each affected route loads → authenticated API data renders → a filter or pagination control changes visible state → no placeholder, framework overlay, or relevant console error appears.

Use the repository Playwright workflow at 1366×768 and 1920×1080 for `/overview`, `/anomalies`, `/orders`, `/reviews`, `/runtime`, `/memory`, `/operations`, and `/monitor`. Capture temporary screenshots outside the repository and inspect clipping, overflow, source badges, tables, drawers, filters, and page identity.

- [ ] **Step 5: Run final diff and secret scans**

```powershell
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' diff --check
rg -n "Authorization: Bearer|MYSQL_PASSWORD=.+|DEVELOPMENT_JWT_SECRET=.+" backend frontend docs -g '!*.example'
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' status --short
```

Expected: no diff errors, no committed secret values, and only intended files changed alongside pre-existing user work.

- [ ] **Step 6: Commit the verified integration result**

```powershell
git add backend frontend docs/superpowers/specs/2026-08-29-real-workspace-read-models-design.md docs/superpowers/plans/2026-08-29-real-workspace-read-models.md
git commit -m "feat: populate live CountyFlow workspaces"
```

If Git identity remains absent, do not alter it; report the commit as the only blocked verification item.

## Plan Self-Review

- Every requirement in the approved design maps to a numbered task.
- Backend types and method names are consistent across repository, service, API, and frontend client tasks.
- All new production behavior has a named failing test and an explicit RED command before implementation.
- Development seeds never create terminal execution data.
- API mode never falls back to Mock.
- Final browser QA covers every route shown in the reported screenshots.
