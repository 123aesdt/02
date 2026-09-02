# CountyFlow V2-F Frontend Productization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Productize every accepted CountyFlow V2 capability in the existing frontend with real API/WebSocket evidence, accessible interactions, browser proof, and no backend semantic change.

**Architecture:** Preserve the current React/Vite shell and add focused V2 presentation components. API mode consumes `/health`, existing read endpoints, and task-event history without mock fallback; mock mode uses explicitly labelled demo fixtures. Backend changes are limited to existing safe fields in read DTOs and events.

**Tech Stack:** React, TypeScript, Vite, Vitest, Testing Library, Playwright, FastAPI, Pydantic, pytest, existing WebSocket task events, CSS, Lucide React.

**Spec:** `docs/superpowers/specs/2026-08-28-v2-f-frontend-productization-design.md`

## Global Constraints

- Preserve existing navigation, theme, routes, backend algorithms, storage responsibilities, and asynchronous execution path.
- API mode must never fall back to mock data.
- Verified Acceptance values must be labelled as evidence, not live monitoring.
- Backend additions are limited to safe existing DTO/event fields.
- Use the canonical eight-agent order with Graph Memory between Entity Memory and Environment.
- Do not rerun V2-E heavy suites unless backend semantics change.
- Do not commit, merge, create a PR, or modify Git author configuration.

---

### Task 1: Safe backend read contracts

**Files:**
- Modify: `backend/app/api/v1/runtime_thread_schemas.py`
- Modify: `backend/app/runtime_threads/service.py`
- Modify: `backend/app/api/v1/memory_schemas.py`
- Modify: `backend/app/api/v1/memory_mutations.py`
- Modify: `backend/app/events/graph_adapter.py`
- Test: `backend/tests/api/test_runtime_threads.py`
- Test: `backend/tests/api/test_memory_mutations.py`
- Test: `backend/tests/api/test_task_events.py`

**Interfaces:**
- Produces safe JSON fields consumed by the V2-F React types and event panels.
- Does not change commands, persistence, routing, checkpointing, or graph execution.

- [ ] Write behavior tests asserting worker/update metadata, fact/mutation metadata, routing evidence, and audit evidence.
- [ ] Run the three targeted pytest files and confirm the new assertions fail because fields are absent.
- [ ] Add the smallest schema/service/adapter projections from already-existing model/state values.
- [ ] Rerun targeted tests and confirm they pass.
- [ ] Refactor repeated safe serialization only if duplication is introduced; rerun tests.
- [ ] Inspect `git diff` for Task 1 scope.

### Task 2: Provenance-aware frontend data contracts

**Files:**
- Create: `frontend/src/types/v2-product.ts`
- Create: `frontend/src/mocks/v2-product-data.ts`
- Create: `frontend/src/services/api/health-client.ts`
- Modify: `frontend/src/types/memory.ts`
- Modify: `frontend/src/types/runtime-thread.ts`
- Modify: `frontend/src/types/task-events.ts`
- Modify: `frontend/src/hooks/use-backend-health.ts`
- Test: `frontend/tests/v2-data-contracts.test.ts`
- Test: `frontend/tests/mock-service.test.ts`

**Interfaces:**
- Produces `DataProvenance`, verified baseline fixtures, graph view models, and complete safe API/event types.

- [ ] Write tests that reject API-to-mock fallback and verify complete response mapping.
- [ ] Run targeted Vitest tests and confirm expected contract failures.
- [ ] Add types, explicit demo fixtures, health client, and non-fallback hooks.
- [ ] Rerun targeted tests to GREEN and refactor mapping helpers.

### Task 3: Dashboard and eight-agent product surfaces

**Files:**
- Create: `frontend/src/components/v2-capability-summary.tsx`
- Modify: `frontend/src/pages/dashboard-page.tsx`
- Modify: `frontend/src/pages/agents-page.tsx`
- Modify: `frontend/src/components/agent-pipeline.tsx`
- Modify: `frontend/src/hooks/use-task-events.ts`
- Modify: `frontend/src/services/dispatch-service.ts`
- Test: `frontend/tests/dashboard-v2.test.tsx`
- Test: `frontend/tests/agents-v2.test.tsx`
- Test: `frontend/tests/task-events-lifecycle.test.tsx`

**Interfaces:**
- Dashboard consumes live health or Verified Acceptance, never fake live metrics.
- Agents consumes a task ID and canonical WebSocket execution state in API mode.

- [ ] Write failing behavior tests for the capability summary, provenance labels, canonical eight-agent order, graph detail, and API event-driven state.
- [ ] Confirm RED using targeted Vitest files.
- [ ] Implement the minimal summary and agent execution surfaces.
- [ ] Confirm GREEN, then remove obsolete seven-agent/mock-live copy.

### Task 4: Memory tabs, graph visualization, and path inspector

**Files:**
- Create: `frontend/src/components/memory-tabs.tsx`
- Create: `frontend/src/components/graph-memory-view.tsx`
- Create: `frontend/src/components/graph-visualization.tsx`
- Create: `frontend/src/components/graph-path-inspector.tsx`
- Create: `frontend/src/hooks/use-graph-memory-events.ts`
- Modify: `frontend/src/pages/memory-page.tsx`
- Modify: `frontend/src/styles/memory-control.css`
- Test: `frontend/tests/memory-tabs.test.tsx`
- Test: `frontend/tests/graph-memory-view.test.tsx`

**Interfaces:**
- Consumes task WebSocket graph events and emits a display-only bounded `GraphMemoryViewModel`.
- Node selection feeds the property inspector; no traversal or backend write is performed.

- [ ] Write failing tests for tab semantics, Demo/API provenance, entities/relations, keyboard node selection, bounded paths, and all inspector evidence fields.
- [ ] Confirm RED with focused Vitest commands.
- [ ] Implement the SVG graph and inspectors without a new dependency.
- [ ] Confirm GREEN and refactor shared status/source components.

### Task 5: Shared Memory Control Plane lifecycle

**Files:**
- Create: `frontend/src/components/shared-memory-control.tsx`
- Create: `frontend/src/components/projection-status.tsx`
- Modify: `frontend/src/pages/memory-page.tsx`
- Modify: `frontend/src/services/api/memory-client.ts`
- Modify: `frontend/src/styles/memory-control.css`
- Test: `frontend/tests/memory-control-plane.test.tsx`

**Interfaces:**
- Consumes the existing fact read endpoint and the safe fields from Task 1.

- [ ] Add failing tests for canonical metadata, STAGED/FINALIZING not-active copy, per-projection labels, and full mutation history.
- [ ] Confirm RED.
- [ ] Implement the read-only Shared Control tab and labelled mock-mode demo.
- [ ] Confirm GREEN and refactor table formatting.

### Task 6: Runtime thread, checkpoint, override, downstream, and audit evidence

**Files:**
- Create: `frontend/src/components/checkpoint-timeline.tsx`
- Modify: `frontend/src/components/runtime-thread-panel.tsx`
- Modify: `frontend/src/components/runtime-event-timeline.tsx`
- Modify: `frontend/src/components/runtime-override-dialog.tsx`
- Modify: `frontend/src/components/runtime-override-history.tsx`
- Modify: `frontend/src/components/capacity-evidence-panel.tsx`
- Modify: `frontend/src/pages/api-dispatch-detail-page.tsx`
- Modify: `frontend/src/styles/index.css`
- Test: `frontend/tests/runtime-thread-panel.test.tsx`
- Test: `frontend/tests/runtime-workbench.test.tsx`
- Test: `frontend/tests/checkpoint-timeline.test.tsx`
- Test: `frontend/tests/dispatch-v2-evidence.test.tsx`

**Interfaces:**
- Combines runtime-thread history, override history, and live task events for presentation only.

- [ ] Write failing tests for worker/update fields, checkpoint/version distinction, chronological override entries, focus/Escape behavior, routing evidence, and audit details.
- [ ] Confirm RED with focused tests.
- [ ] Implement the smallest presentational changes and safe event-field rendering.
- [ ] Confirm GREEN; refactor semantic event labels and focus utility while retaining behavior.

### Task 7: Monitoring V2

**Files:**
- Create: `frontend/src/components/verified-baseline-panel.tsx`
- Modify: `frontend/src/pages/monitor-page.tsx`
- Modify: `frontend/src/styles/index.css`
- Test: `frontend/tests/monitoring-v2.test.tsx`

**Interfaces:**
- Live backend data comes only from `/health`; historical metrics come only from the immutable verified-baseline fixture.

- [ ] Write failing tests for seven named runtime services, NOT EXPOSED state, Neo4j, checkpoint/override/shared-memory sections, and Verified Acceptance labels.
- [ ] Confirm RED.
- [ ] Implement the monitoring layout and provenance labels.
- [ ] Confirm GREEN and remove old misleading mock telemetry.

### Task 8: Browser E2E and screenshots

**Files:**
- Create: `frontend/e2e/v2f-productization.spec.ts`
- Modify: existing V2 E2E support only when needed for deterministic setup
- Create: `docs/verification/v2-f/screenshots/*.png`

**Interfaces:**
- Uses the existing Playwright workflow because the Browser plugin is absent and the user approved Playwright fallback.

- [ ] Define the target flow: Dashboard → Agents → Memory tabs → real task Dispatch Detail → intervention → downstream evidence → Monitoring.
- [ ] Add E2E assertions for normal V2, graph, shared memory, checkpoint, eligible override, NORMAL→BROKEN, capacity BROKEN, routing review, override history, audit, and monitoring.
- [ ] Run the new spec and capture its initial failures.
- [ ] Fix only real product/browser defects, rerunning focused tests after each fix.
- [ ] Capture the 12 required screenshots at 1440 and validate 1920 layout.
- [ ] Inspect every saved screenshot and reject blank, loading, cropped, wrong-state, or error-overlay captures.

### Task 9: Final audit and gates

**Files:**
- Create: `docs/verification/v2-f/frontend-v2-productization.md`

**Interfaces:**
- Maps each V2 capability to backend status, frontend surface, real data source, WebSocket/API evidence, screenshot, and tests.

- [ ] Write the A–O before/after audit and final completeness matrix from actual evidence.
- [ ] Run frontend targeted tests, full tests, lint, and build.
- [ ] Run targeted backend contract tests, full pytest, and Ruff.
- [ ] Run `scripts/check.ps1` and Docker nine-service checks without rerunning V2-E heavy benchmarks.
- [ ] Run the existing secret artifact scan and require zero findings.
- [ ] Run `git diff --check`, `git diff --cached --check`, and `git status`.
- [ ] Inspect the final diff against the spec and report only commands actually run.
