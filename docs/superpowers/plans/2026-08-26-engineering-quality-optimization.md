# CountyFlow Engineering Quality Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CountyFlow's local quality gate trustworthy, runtime profiles explicit, warnings understood, and repository documentation ready for real Docker acceptance without adding business features.

**Architecture:** Keep the seven-agent graph and business rules unchanged. Strengthen the existing PowerShell gate with checked child steps, express the current deterministic Docker runtime through validated settings and safe health diagnostics, then align documentation and ignore rules with the actual repository state.

**Tech Stack:** PowerShell, Python 3.12, Pydantic Settings, FastAPI, pytest, React 19, Vitest, TypeScript, Vite, Docker Compose static configuration.

**Spec:** User-approved “P0 ENGINEERING QUALITY OPTIMIZATION” task prompt dated 2026-08-26.

## Global Constraints

- Do not add agents, pages, Locust workloads, real provider integrations, or Docker execution.
- Do not modify seven-agent decisions, routing rules, or memory semantics.
- Use TDD for behavior changes and preserve at least 212 backend and 31 frontend passing tests.
- Do not change Git identity or create a commit.
- Keep real Redis, MySQL, Qdrant, Docker, multi-worker, and semantic-recall claims explicitly unverified.

---

### Task 1: Trustworthy PowerShell Quality Gate

**Files:**
- Modify: `scripts/check.ps1`
- Create: `scripts/frontend-lint.ps1`
- Create: `scripts/frontend-test.ps1`
- Create: `scripts/frontend-build.ps1`
- Create: `backend/tests/unit/test_check_script.py`

**Interfaces:**
- Consumes: repository-local Python virtual environment and frontend npm scripts.
- Produces: `scripts/check.ps1` returning the first non-zero mandatory-step exit code and stopping later steps.

- [ ] Write subprocess contract tests that copy the real gate into a temporary directory and supply controlled success/failure child scripts.
- [ ] Run the focused pytest file and confirm the failure case currently returns zero.
- [ ] Add a minimal `Invoke-CheckedStep` helper and five mandatory backend/frontend child steps.
- [ ] Rerun the focused tests and confirm success, failure, and no-overwrite contracts pass.

### Task 2: Warning Cleanup and Attribution

**Files:**
- Modify: `frontend/tests/task-events-lifecycle.test.tsx`
- Modify: backend test imports only if direct Starlette `TestClient` removes the third-party warning without dependency upgrades.

**Interfaces:**
- Consumes: existing Vitest lifecycle tests and FastAPI/Starlette test client.
- Produces: warning-free owned React state transitions and an accurately classified backend deprecation.

- [ ] Reproduce the React warnings and wrap only state-producing fake WebSocket actions in awaited `act` calls.
- [ ] Rerun the focused frontend test and verify stderr contains no owned `act(...)` warning.
- [ ] Reproduce the backend warning, inspect installed package source/version, and test a direct Starlette import.
- [ ] Apply only the small import adjustment if it removes the warning; otherwise retain and document it as third-party.

### Task 3: Explicit Runtime Profiles and Provider Safety

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/runtime.py`
- Modify: `backend/tests/unit/test_settings.py`
- Modify: `backend/tests/unit/test_health.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Interfaces:**
- Produces: validated `runtime_profile`, backend labels, a secret-free `runtime_summary`, and health diagnostics using only labels.

- [ ] Add failing tests for docker-dev allowances, production rejection of fake/dev providers, and safe diagnostics.
- [ ] Run focused tests and confirm failures describe missing runtime-profile behavior.
- [ ] Implement minimal Pydantic validation and diagnostic labels without changing graph decisions.
- [ ] Mark Compose explicitly as `docker-dev` with MySQL/server infrastructure and deterministic providers.
- [ ] Rerun focused settings, health, and Docker configuration tests.

### Task 4: Documentation and Repository Hygiene

**Files:**
- Modify: `README.md`
- Modify: `Makefile`
- Modify: `.gitignore`
- Modify: `backend/tests/unit/test_docker_runtime_files.py`

**Interfaces:**
- Produces: current-state quick start, verification-level language, current gate targets, runtime storage exclusions, and static consumer/profile assertions.

- [ ] Update README with architecture, Local/Full Runtime truth, verification levels, and current measured test baselines.
- [ ] Replace only obsolete operational Phase 0 Makefile messages with current commands.
- [ ] Extend ignore rules for coverage, SQLite variants, Redis persistence, and repository-local runtime storage.
- [ ] Add static assertions that workers have distinct names and Compose is explicitly docker-dev.

### Task 5: Full Verification and Initial Commit Readiness

**Files:** No production files beyond Tasks 1–4.

- [ ] Run backend Ruff and full pytest; require at least 212 passing tests.
- [ ] Run frontend lint, tests, and production build; require at least 31 passing tests and no owned act warning.
- [ ] Run `scripts/check.ps1` normally and the gate contract tests.
- [ ] Run Python compileall, both Git diff checks, and final status.
- [ ] Inspect staged/untracked paths and tracked-content secret patterns without printing secret values.
- [ ] Record Docker as static-ready only and all real-runtime claims as not verified.
