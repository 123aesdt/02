# Restore Latest Worktree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the complete September 9 implementation into the runnable project without losing the September 10 design specification or startup repairs.

**Architecture:** Preserve both dirty worktrees as commits before integration. Merge the feature worktree into a dedicated recovery branch created from current `main`, resolve conflicts by retaining the newer business implementation and the current offline-safe startup behavior, then rebuild the full Docker stack from the integrated tree.

**Tech Stack:** Git worktrees, PowerShell, Docker Compose, FastAPI, Redis Streams, MySQL, Qdrant, React, TypeScript, Vite, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-10-vehicle-rescue-maintenance-map-system-design.md`

## Global Constraints

- Preserve every tracked and intentional untracked source/test file from `codex/县域物流异常调度`.
- Do not commit `frontend/test-results/` transient Playwright output.
- Preserve the current startup repair, database compatibility migrations, and September 10 map/maintenance design specification.
- Never delete either source worktree during recovery.
- Run the repository verification gates before reporting completion.

---

### Task 1: Preserve Both Dirty States

**Files:**
- Modify: current recovery branch Git history
- Modify: `codex/县域物流异常调度` Git history

- [ ] **Step 1: Create `codex/restore-latest-version` from current `main`**

Run: `git switch -c codex/restore-latest-version`

- [ ] **Step 2: Commit the verified startup repair and this recovery plan**

Stage only the launcher, Docker, migration, test, and plan files; leave `.superpowers/` untouched.

- [ ] **Step 3: Commit the September 9 feature-worktree source, tests, and evidence**

Stage tracked changes and intentional untracked files while excluding `frontend/test-results/`.

- [ ] **Step 4: Confirm both worktrees are preserved**

Run: `git status --short --branch` in both worktrees and record the resulting commit ids.

### Task 2: Integrate the Latest Feature Branch

**Files:**
- Merge: `codex/县域物流异常调度` into `codex/restore-latest-version`
- Resolve: `docker-compose.yml` and any source conflicts reported by Git

- [ ] **Step 1: Merge with a non-fast-forward merge commit**

Run: `git merge --no-ff codex/县域物流异常调度`

- [ ] **Step 2: Resolve conflicts without dropping either requirement set**

Keep the feature branch's fleet/routing behavior and the recovery branch's offline-safe image preparation and Qdrant healthcheck.

- [ ] **Step 3: Inspect the integrated diff and conflict markers**

Run: `git diff --check` and search tracked files for unresolved merge markers.

### Task 3: Verify the Integrated Project

**Files:**
- Test: `backend/tests/`
- Test: `frontend/tests/`
- Build: `frontend/`

- [ ] **Step 1: Run backend lint and tests**

Run: `ruff check backend` and `pytest` using the project's configured Python environment.

- [ ] **Step 2: Run frontend lint, unit tests, and production build**

Run from `frontend`: `npm run lint`, `npm test -- --run`, and `npm run build`.

- [ ] **Step 3: Run Git whitespace validation**

Run: `git -c safe.directory=<workspace> diff --check`.

### Task 4: Rebuild and Confirm the Restored UI

**Files:**
- Runtime: Docker Compose services
- UI: `http://localhost:5173/overview`

- [ ] **Step 1: Rebuild the full stack from the integrated recovery branch**

Run: `powershell -ExecutionPolicy Bypass -File scripts/start-full.ps1`.

- [ ] **Step 2: Check service health and HTTP endpoints**

Confirm frontend, backend, Redis, MySQL, Qdrant, Neo4j, workers, Prometheus, and Grafana are running, and frontend/backend endpoints respond successfully.

- [ ] **Step 3: Verify the restored page in the browser**

Open `/overview`, confirm the September 9 navigation and map pages are present, and capture the rendered state if browser tooling is available.
