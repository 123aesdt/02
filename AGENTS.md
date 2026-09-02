# CountyFlow AI Engineering Rules

## Project goal

CountyFlow AI is a deployable county logistics anomaly identification and intelligent dispatch system. The production path is asynchronous: frontend → FastAPI → Redis Streams → Worker → LangGraph → MySQL/Qdrant/external providers → WebSocket or status query → frontend.

## Phase and modification rules

- Phase 0 contains only project structure, design, test strategy, automation gates, and UI concept assets. Do not add business endpoints, a running graph, or completed React pages in this phase.
- Keep modules single-purpose. Agents must consume narrow application interfaces; they must not import Redis, SQLAlchemy, Qdrant, or a vendor SDK directly.
- Preserve user-supplied requirements and this file. Explain the affected scope before each substantive change and inspect `git diff` after each phase.
- Use TDD for Phase 1 onward: write a behavior-level failing test, run it, implement the smallest real behavior, then rerun it. Never weaken a test merely to pass it.

## Safety and secrets

- Read keys only from environment variables or an untracked `.env`; never hard-code, commit, return, or log a secret.
- `.env` remains ignored. Commit only `.env.example` with empty values.
- Normalize provider and external-API failures without exposing request authorization headers or key material.

## Redis Streams and worker rules

- API handlers only validate, persist task creation, publish with `XADD`, and return a task id. They never synchronously execute LangGraph.
- Use consumer groups, `XACK` only after durable terminal-state persistence, bounded retries, pending recovery via `XAUTOCLAIM`, cancellation-safe shutdown, and real Redis in integration tests.
- Require a stable `task_id` and `idempotency_key`; Redis is not the long-term source of truth. Worker restarts must not create duplicate dispatches.

## Persistence and concurrency rules

- MySQL is the source of truth for orders, tasks, dispatches, and audit data. Qdrant is only Entity-Relation vector memory.
- Dispatch rows use SQLAlchemy `version_id_col`. Convert `StaleDataError` to HTTP 409; do not emulate optimistic locking with a Python equality check.
- Use `Decimal` for distance/cost values where precision matters.

## Providers and resilience rules

- LangGraph nodes depend on `LLMProvider`; memory services depend on `EmbeddingProvider`. The initial production implementation is only OpenAI-Compatible.
- Test doubles are limited to test environments. Production services use real Redis, MySQL, and Qdrant.
- Weather, road, LLM, and embedding requests use explicit async timeouts. Weather/road failure opens a circuit breaker and returns a documented static-route fallback in under one second.

## Required verification

- Phase 0: `make lint`, `make test`, `make check`, and design scans must pass without claiming runtime services were tested.
- Phase 1 onward: run `ruff check backend`, `pytest`, frontend lint/test/build, and targeted integration tests against Docker dependencies.
- Before completion: run `git -c safe.directory=<workspace> diff --check` and record only actual command output.
