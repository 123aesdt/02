# CountyFlow V2-G2 Security Hardening Implementation Plan

> **Execution gate:** Do not execute this plan until the user explicitly approves V2-G2 TDD implementation.

**Goal:** Add unified authenticated principals, exact RBAC/resource admission, secure task WebSockets, Redis rate limiting, security audit/metrics, browser auth UX, and production fail-closed configuration without changing business algorithms or expanding the 11-service topology.

**Architecture:** FastAPI validates a short-lived OIDC-compatible Bearer JWT through an `AuthenticationProvider`, maps allowlisted claims to an immutable principal, applies reusable permission/resource admission, then calls unchanged business policies. Redis owns ephemeral revocation, atomic one-time WebSocket tickets, and atomic per-principal token buckets. MySQL stores append-only security audit. React holds the access token in memory and uses backend-authoritative route/action guards.

**Technology:** Python 3.12, FastAPI, Pydantic, PyJWT with cryptographic extras, HTTPX/JWKS, Redis Lua, SQLAlchemy/Alembic/MySQL, Prometheus/Grafana, React/TypeScript/Vitest/Playwright, Docker Compose.

**Frozen constraints:** TDD for every behavior; no Keycloak/Auth0/user/password service; no new container; no business decision change; no Mock fallback in API mode; no secret read/print/commit; no commits, merge, PR, or Git author change unless separately requested.

---

## Task 1: Security domain, RBAC contract, and fail-closed configuration

**Files:**

- Create: `backend/app/security/__init__.py`
- Create: `backend/app/security/models.py`
- Create: `backend/app/security/permissions.py`
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`
- Modify: `.docker.env.example`
- Test: `backend/tests/security/test_models.py`
- Test: `backend/tests/security/test_permissions.py`
- Test: `backend/tests/security/test_security_config.py`

**RED**

1. Add `test_principal_from_auth_provider` for immutable typed `AuthenticatedPrincipal` and safe public projection.
2. Add a table-driven `ROLE_PERMISSION_MATRIX` contract asserting Supervisor override, Dispatcher no override, Auditor no mutation, Operator no dispatch/override, and Admin explicit union.
3. Add `test_production_dev_auth_rejected`, missing-provider, incomplete OIDC, wildcard production CORS, too-short dev secret, and docker-dev signed-provider requirements.
4. Run:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests/security/test_models.py tests/security/test_permissions.py tests/security/test_security_config.py -q
```

Confirm failure because the security domain/settings do not exist.

**GREEN**

1. Define closed `Role`, `Permission`, `AuthMethod`, `AuthenticatedPrincipal`, and safe principal DTO values.
2. Define one immutable role matrix with the exact mapping from `docs/permissions.md`.
3. Add settings for authentication provider, issuer, audience, JWKS/public-key boundary, algorithms, leeway, access TTL, revocation namespace, dev issuer/secret, CORS/security profiles, audit retention, body caps and named rate policies.
4. Validate profiles so production accepts only the production provider and docker-dev never implies admin.
5. Add only empty/documented configuration names to examples; never add a secret default.
6. Rerun the focused tests and Ruff.

**REFACTOR**

- Keep role expansion in one function and configuration validation in `core/config.py`; do not duplicate permission strings in routes.
- Confirm State models and business DTOs remain unchanged.

## Task 2: JWT AuthenticationProvider and revocation boundary

**Files:**

- Modify: `backend/pyproject.toml`
- Create: `backend/app/security/protocols.py`
- Create: `backend/app/security/credentials.py`
- Create: `backend/app/security/jwt_provider.py`
- Create: `backend/app/security/revocation.py`
- Test: `backend/tests/security/test_jwt_provider.py`
- Test: `backend/tests/security/test_revocation.py`
- Integration test: `backend/tests/integration/test_real_redis_security.py`

**RED**

1. Write `test_missing_token_401` contract at the credentials/provider boundary.
2. Write `test_invalid_token_401`, `test_expired_token_401`, `test_wrong_audience_401`, wrong issuer, `alg=none`, disallowed algorithm, premature `nbf`, allowed 30-second skew, unknown role ignored, and unknown `kid` bounded refresh tests.
3. Test `jti` revocation uses a digest key and remaining-lifetime TTL; no raw token/JTI is persisted.
4. Run the focused tests and confirm failures.

**GREEN**

1. Add a bounded dependency such as `PyJWT[crypto]>=2.10,<3`; use the library's verified decoding rather than custom signature comparison.
2. Implement Bearer extraction with one accepted scheme and safe errors.
3. Implement production JWKS/public-key and docker-dev HMAC adapters behind `AuthenticationProvider`.
4. Validate `iss`, `aud`, `sub`, `iat`, `nbf`, `exp`, `jti`, configured algorithm, `kid`, and 30-second leeway.
5. Implement Redis `RevocationStore`; provider failure never creates a principal.
6. Verify the real Redis TTL path without external OIDC network calls.

**REFACTOR**

- Separate claim verification from allowlisted role mapping.
- Ensure provider exceptions carry stable enums only, not headers/token/claims.

## Task 3: FastAPI dependencies, safe errors, and application bootstrap

**Files:**

- Create: `backend/app/security/dependencies.py`
- Create: `backend/app/security/errors.py`
- Create: `backend/app/api/v1/auth.py`
- Create: `backend/app/api/v1/auth_schemas.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/api/test_authentication.py`
- Test: `backend/tests/security/test_error_safety.py`

**RED**

1. API-test `GET /api/v1/auth/me` and one protected probe for missing, malformed, expired and valid tokens.
2. Add `test_permission_denied_403` and assert authentication failure is 401, not 403.
3. Add `test_error_response_no_secret` covering provider/JWT exceptions and normalized 500/503.
4. Add startup tests proving production fails closed and no external auth outage activates development auth.
5. Confirm failures.

**GREEN**

1. Implement `get_current_principal` and `require_permission(permission)` dependency factories.
2. Add safe 401 `WWW-Authenticate: Bearer`, 403, 429, and 503 envelopes.
3. Add `/auth/me` safe projection and `/auth/logout` revocation of caller JTI.
4. Build/inject exactly one authentication provider in `create_app`; production-invalid settings stop startup.
5. Add `Authorization` to explicit CORS allowed headers while keeping credentials false.

**REFACTOR**

- Centralize exception-to-response mapping; route files do not decode tokens or hand-write permission membership checks.

## Task 4: Append-only security audit

**Files:**

- Create: `backend/app/security/audit_models.py`
- Create: `backend/app/security/audit_protocols.py`
- Create: `backend/app/security/sqlalchemy_audit_repository.py`
- Create: `backend/app/security/audit_service.py`
- Create: `backend/alembic/versions/20260828_06_security_audit.py`
- Modify: `backend/app/core/database.py` or metadata import boundary as required
- Test: `backend/tests/security/test_security_audit.py`
- Test: `backend/tests/security/test_security_audit_repository.py`

**RED**

1. Add `test_security_audit_denied` for bounded fields and stable event/reason enums.
2. Test append-only behavior, 180-day configured retention range, subject known/unknown, request ID and route template.
3. Test raw token/header/body/exception fields are structurally impossible or rejected.
4. Test a failed audit write does not convert a denial to allow and blocks admitted high-risk mutation before business service invocation.
5. Confirm migration/repository tests fail.

**GREEN**

1. Add a minimal indexed MySQL table for event ID/type, optional subject, permission, route class/template, status, reason code, request ID, normalized remote address, and timestamps.
2. Implement typed append and bounded retention deletion; no update API.
3. Connect authentication/authorization failure hooks through a narrow `SecurityAuditSink`.
4. Keep successful Runtime/Memory result truth in existing business audit while recording admission separately.

**REFACTOR**

- Ensure audit write ownership is outside business repositories and that route/body objects never cross the protocol.

## Task 5: Protect existing APIs and remove actor spoofing

**Files:**

- Modify: `backend/app/api/v1/dispatch_tasks.py`
- Modify: `backend/app/api/v1/runtime_threads.py`
- Modify: `backend/app/api/v1/runtime_overrides.py`
- Modify: `backend/app/api/v1/memory_mutations.py`
- Modify: `backend/app/api/v1/memory_schemas.py`
- Modify: `backend/app/api/v1/observability.py`
- Modify: `backend/app/runtime_threads/auth.py`
- Modify: `backend/app/runtime_threads/protocols.py`
- Modify: `backend/app/runtime_threads/service.py`
- Modify: `backend/app/runtime_overrides/service.py`
- Modify: `backend/app/runtime_overrides/query_service.py`
- Modify: `backend/app/shared_memory/service.py`
- Add/modify tests: existing files under `backend/tests/api/`, `runtime_overrides/`, `runtime_threads/`, `shared_memory/`, and `observability/`

**RED**

1. Add exact endpoint permission table tests from `docs/permissions.md`.
2. Add `test_runtime_override_requires_permission`, `test_memory_mutation_requires_permission`, `test_monitor_requires_permission`, and `test_audit_requires_permission`.
3. Add `test_operator_identity_from_principal` and `test_client_cannot_spoof_operator`; body actor must be removed/rejected.
4. Assert `human_confirmed=true` without `memory:mutate` is 403 and no mutation service call occurs.
5. Assert Dispatcher direct override, Auditor direct dispatch/mutation, and Operator direct override are 403.
6. Assert existing version/stability/old-value/allowlist/idempotency tests still fail/pass for the same reasons after authorized admission.
7. Confirm RED before changing production routes/services.

**GREEN**

1. Add principal/permission dependencies to every current protected route.
2. Adapt narrow runtime/resource authorizers to consume the request principal and canonical resource metadata rather than returning global trusted identity.
3. Build Runtime Override and Shared Memory actors server-side; remove `operator_id` from public mutation DTO.
4. Apply separate minimized versus audit response projections for override/memory history.
5. Replace observability's requestless trusted context with the unified principal while preserving `NO_PERMISSION` semantics.
6. Preserve exact existing business status codes and policies after admission.

**REFACTOR**

- Use one dependency registry/helper; no inline permission string checks.
- Keep repository/driver/session objects out of request/principal/state models.

## Task 6: Redis token-bucket rate limiter and idempotent retry charging

**Files:**

- Create: `backend/app/security/rate_limit.py`
- Create: `backend/app/security/redis_rate_limiter.py`
- Create: `backend/app/security/rate_limit_dependency.py`
- Modify: relevant API routes and application idempotency lookup boundaries
- Test: `backend/tests/security/test_rate_limit.py`
- Integration test: `backend/tests/integration/test_real_redis_rate_limit.py`

**RED**

1. Add `test_rate_limit_dispatch`, `test_rate_limit_override`, `test_rate_limit_memory_mutation`, `test_rate_limit_429`, `test_rate_limit_retry_after`, and `test_rate_limit_per_principal`.
2. Test atomic concurrent consumption, bounded operation-class allowlist, digest key, refill/burst math, and acceptable reset after Redis restart.
3. Test exact same-principal/same-fingerprint idempotent replay is not repeatedly charged; conflict/new requests are charged.
4. Test Redis outage: dispatch/override/mutation/ticket writes fail closed; observability read uses only the explicit local emergency cap.
5. Confirm RED.

**GREEN**

1. Implement the token bucket as one Lua operation returning allowed/remaining/reset/retry.
2. Add reusable named-operation dependencies and consistent headers/error envelope.
3. Add a narrow read-only idempotency admission lookup before rate debit; never trust a key without principal/fingerprint match.
4. Instrument safe audit events without subject metric labels.

**REFACTOR**

- Keep Redis client details out of routes and business services; centralize fail-open/closed policy by operation class.

## Task 7: One-time WebSocket tickets

**Files:**

- Create: `backend/app/security/ws_ticket_models.py`
- Create: `backend/app/security/ws_ticket_service.py`
- Create: `backend/app/security/redis_ws_ticket_repository.py`
- Create: `backend/app/api/v1/ws_tickets.py`
- Create: `backend/app/api/v1/ws_ticket_schemas.py`
- Modify: `backend/app/api/v1/task_events.py`
- Test: `backend/tests/security/test_ws_ticket_service.py`
- Test: `backend/tests/api/test_task_websocket.py`
- Integration test: `backend/tests/integration/test_real_redis_ws_tickets.py`

**RED**

1. Add `test_websocket_requires_auth`, `test_ws_ticket_single_use`, `test_ws_ticket_expired`, and `test_ws_ticket_wrong_scope`.
2. Test 256-bit opaque value, digest-only Redis storage, 45-second TTL, principal/permission/task binding, atomic concurrent consume, and fresh-ticket reconnect.
3. Assert no access token is accepted in a WebSocket query and ticket query is absent/redacted from access logs.
4. Confirm anonymous current WebSocket fails the new tests.

**GREEN**

1. Implement authenticated/rate-limited `POST /api/v1/ws-tickets`.
2. Store/consume tickets atomically in Redis and accept sockets only after exact task-scope authorization.
3. Return close codes 4401/4403/4408 without details; retain existing event replay/order/dedupe behavior after acceptance.
4. Add safe rejection audit/metric hooks.

**REFACTOR**

- Keep event broker untouched by ticket logic; ticket service is an admission boundary only.

## Task 8: Redaction, body limits, headers, CORS, docs, and secret isolation

**Files:**

- Create: `backend/app/security/redaction.py`
- Create: `backend/app/security/http_middleware.py`
- Modify: `backend/app/observability/logging.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/v1/schemas.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `.docker.env.example`
- Test: `backend/tests/security/test_redaction.py`
- Test: `backend/tests/security/test_http_security.py`
- Modify/test: `backend/tests/api/test_cors.py`
- Modify/test: `backend/tests/unit/test_docker_runtime_files.py`

**RED**

1. Add `test_security_log_redaction` for nested Authorization/Cookie/token/key/password/SecretStr/JWT/basic-auth/credential URL and raw query handling.
2. Add `test_error_response_no_secret`, `test_cors_production_explicit`, `test_security_headers`, and `test_body_size_limit`.
3. Test production CSP/HSTS profile, docker-dev exact HMR/connect exceptions, clickjacking denial, public minimal health, internal metrics, and production-disabled docs.
4. Test anomaly description 2,000 characters and route-specific 16/8/32/2 KiB body caps.
5. Add Compose contract that Neo4j uses `NEO4J_PASSWORD`, never `MYSQL_PASSWORD`; distinct examples remain blank/ignored.
6. Confirm failures.

**GREEN**

1. Implement recursive fail-safe redaction shared by logs/audit/errors and route-template safe access logging.
2. Implement pre-parse body cap and profile-aware response headers.
3. Keep production CORS explicit/Bearer credentials false; disable docs in production.
4. Correct Neo4j secret variable wiring without inspecting a real value.
5. Extend field bounds without weakening current schemas.

**REFACTOR**

- Middleware order is documented/tested: correlation → safe error/body/security controls → auth/route admission → metrics response accounting, with actual ASGI wrapping order verified.
- Redactor failure drops unsafe data rather than logging original values.

## Task 9: Security metrics, alerts, Grafana section, and read summary

**Files:**

- Modify: `backend/app/observability/catalog.py`
- Modify: `backend/app/observability/labels.py`
- Modify: `backend/app/observability/service.py`
- Modify: `backend/app/api/v1/observability_schemas.py`
- Modify: `monitoring/prometheus/rules/countyflow-alerts.yml`
- Modify: `monitoring/grafana/dashboards/countyflow-v2-operations.json`
- Test: `backend/tests/security/test_security_metrics.py`
- Test: `backend/tests/observability/test_catalog.py`
- Test: `backend/tests/observability/test_observability_api.py`
- Test: `backend/tests/observability/test_monitoring_config.py`

**RED**

1. Test the four exact counter names and only `reason_code,route_class` labels.
2. Test auth failure, 403, 429 and WS reject increment bounded values; subject/IP/token/task are rejected as labels.
3. Test five alerts have minimum-volume guards and `for` duration.
4. Test Grafana Security section and authorized aggregate-only frontend DTO.

**GREEN**

1. Register controlled families through the existing recorder/catalog.
2. Add bounded route/reason enums and no raw subject/event detail.
3. Add alert rules and provisioned Security dashboard panels.
4. Extend the fixed Observability read model for security aggregates under `monitor:read`.

**REFACTOR**

- Reuse V2-G1 recorder failure isolation; security metric failure never changes admission/business outcome.

## Task 10: Frontend AuthContext, API client, route/action guards, and session expiry

**Files:**

- Create: `frontend/src/auth/auth-context.tsx`
- Create: `frontend/src/auth/permissions.ts`
- Create: `frontend/src/auth/route-guard.tsx`
- Create: `frontend/src/hooks/use-auth.ts`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/services/api/client.ts`
- Modify: all specialized clients under `frontend/src/services/api/`
- Modify: `frontend/src/services/task-event-client.ts`
- Modify: `frontend/src/hooks/use-task-events.ts`
- Modify: `frontend/src/components/app-shell.tsx`
- Modify: intervention/memory/monitor/audit components and relevant pages
- Test: new focused Vitest files beside auth/client/components

**RED**

1. Test principal/roles/permissions/status/expiry are held in memory and no local/session storage write occurs.
2. Test shared clients attach Bearer, one 401 clears sensitive state/aborts queries/closes socket/stops retries, and 403 remains `NO_PERMISSION`.
3. Test Dispatcher cannot see/use Override; Supervisor can; Auditor cannot dispatch write; Operator can monitor but not mutate memory; Admin gets all actions.
4. Test Memory read-only, audit-detail restriction, Monitoring no permission, and API mode no Mock fallback.
5. Test visible `DEV AUTH` banner and fresh ticket acquisition for every socket reconnect.
6. Confirm failures.

**GREEN**

1. Implement the in-memory AuthContext and one central authenticated request boundary.
2. Add route/action guards with accessible disabled/no-permission messages.
3. Integrate WS ticket issuance without placing the bearer token in a URL.
4. Add bounded reauthentication/session-expired UX and cancel protected background work.

**REFACTOR**

- Permission logic lives in one frontend module and mirrors the backend contract for UX only; pages do not parse JWTs.

## Task 11: Dev token helper and browser/security Docker E2E

**Files:**

- Create: `scripts/create-dev-token.ps1`
- Create: `scripts/test-security.ps1`
- Create: `scripts/security_integration.py`
- Modify: `scripts/test-browser-e2e.ps1`
- Modify: `scripts/test-docker.ps1`
- Modify: `docker-compose.yml`
- Modify: `一键启动.bat` and/or `scripts/start-dev.ps1` only as needed for documented dev identity selection
- Test: `backend/tests/unit/test_dev_launcher_scripts.py`
- Test: Playwright security specs in existing frontend E2E directory

**RED**

1. Test helper refuses production, requires ignored secret, never prints secret, and produces signed role-limited development JWT.
2. Browser scenarios: Dispatcher dispatch/no override; Supervisor override; Auditor audit/no write; Operator monitoring/no mutation; Admin all.
3. Add session-expiry request-storm, direct API bypass, task-ticket replay/scope, Redis restart, and concurrent override abuse scenarios.
4. Confirm Docker still reports exactly 11 services and no automatic admin.

**GREEN**

1. Implement the safe token helper with explicit role and short TTL; output token only because the helper's purpose is local user handoff, never log it from server/tests/artifacts. Prefer clipboard/stdout warning and ensure CI artifact capture is disabled for the token value.
2. Wire test users through signed docker-dev JWT fixtures.
3. Add repeatable security runner and integrate only after focused layers pass.
4. Preserve the lightweight launcher and visibly mark development auth.

**REFACTOR**

- Do not add a Keycloak/Auth service. Keep credentials in ignored environment and sanitize test artifacts/screenshots.

## Task 12: Full regression, abuse/performance comparison, and delivery evidence

**Files:**

- Modify: `loadtests/` only to add authenticated headers/role setup and explicit rate policy metadata
- Create: `docs/verification/v2-g2/` evidence manifest/raw outputs as used by the approved verification convention
- Update: `docs/security_spec.md`, `docs/permissions.md`, `docs/security-runbook.md`, `README.md`, and `docs/design.md` only for verified final behavior

**RED / precondition capture**

1. Record focused failures before each implementation task. Do not fabricate a single retroactive RED.
2. Capture the unchanged V2-G1/V2-F regression commands and security acceptance criteria.

**GREEN verification sequence**

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m pytest -q

Set-Location ..\frontend
npm run lint
npm test
npm run build
npm run test:e2e

Set-Location ..
powershell -ExecutionPolicy Bypass -File scripts/test-security.ps1
powershell -ExecutionPolicy Bypass -File scripts/test-docker.ps1
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' diff --check
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' diff --cached --check
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' status --short
```

Run the existing repository secret-artifact scan and require `0 findings`. Do not read or print real API keys.

**Security/performance acceptance**

- Real Redis: tickets, token buckets and revocation verified.
- Docker: 11 services, signed non-admin dev JWT, protected HTTP/WS, internal Prometheus, authenticated Grafana.
- Security metrics: real 401/403/429/ticket rejection visible with bounded labels.
- Abuse: override floods return 429 without worker/business collapse.
- Normal authenticated traffic with security ON: QPS `>=200`, API P95 `<300 ms`, unexpected error rate `<0.1%`.
- Compare OFF/ON only where OFF is a controlled benchmark profile; production never disables security.
- Existing V2-A through V2-G1 functional/regression evidence remains valid unless source changes require its targeted rerun.

**REFACTOR / final review**

1. Inspect `git diff` by task area and remove duplicated checks, accidental secrets, raw URLs, unsafe labels, dead trusted-auth branches, and unbounded DTOs.
2. Verify no client can spoof actor, no anonymous socket remains, production cannot choose dev auth, UI is not the sole enforcement, limiter is not IP-only, Grafana is not anonymous, and Prometheus is not public.
3. Update documentation with actual test counts and results only after commands have run. Do not claim V2-G2 COMPLETE from the plan alone.

---

## Required test-name checklist

The implementation must contain or explicitly map these named contracts:

```text
test_principal_from_auth_provider
test_missing_token_401
test_invalid_token_401
test_expired_token_401
test_wrong_audience_401
test_permission_denied_403
test_runtime_override_requires_permission
test_memory_mutation_requires_permission
test_monitor_requires_permission
test_audit_requires_permission
test_operator_identity_from_principal
test_client_cannot_spoof_operator
test_production_dev_auth_rejected
test_websocket_requires_auth
test_ws_ticket_single_use
test_ws_ticket_expired
test_ws_ticket_wrong_scope
test_rate_limit_dispatch
test_rate_limit_override
test_rate_limit_memory_mutation
test_rate_limit_429
test_rate_limit_retry_after
test_rate_limit_per_principal
test_security_audit_denied
test_security_log_redaction
test_error_response_no_secret
test_cors_production_explicit
test_security_headers
test_body_size_limit
```

## Stop point

This document is an implementation plan, not authorization to execute it. Stop after design review and wait for explicit V2-G2 TDD approval.

