# CountyFlow V2-G2 Security Hardening Design

**Status:** DESIGN READY — implementation requires explicit approval

**Date:** 2026-08-28

**Scope:** Security and access-control hardening only. No new business algorithm, IAM product, or service topology change.

## 1. Frozen baseline

V2-G2 preserves the accepted 11-service architecture, asynchronous FastAPI→Redis Streams→two Workers path, eight-agent LangGraph, MySQL/Qdrant/Neo4j memory responsibilities, checkpoint/override semantics, V2-G1 metrics and failure isolation, and frontend API-mode no-Mock contract.

Authentication, authorization, and business validation are separate gates:

```text
authenticated identity
  → permission/resource eligibility
  → security admission (rate/audit)
  → existing idempotency/version/allowlist/stability/business policy
  → existing durable result
```

Having `runtime:override` never bypasses V2-D1. Having `memory:mutate` never makes `human_confirmed=true` sufficient. The full normative details are in `docs/security_spec.md`; the exact matrices are in `docs/permissions.md`.

## 2. Audit result

The current application has no unified request authentication or principal. Runtime Thread/Override and Observability each have a narrow trusted/disabled authorizer, useful as fail-closed precedents but backed by process-global development identities. Dispatch and Shared Memory APIs are not uniformly protected; Shared Memory accepts client `operator_id`; Task WebSocket is anonymous after task-ID existence; frontend has no auth/token store or guards. CORS is explicit with credentials off, secrets are ignored, Prometheus is internal, and Grafana requires environment credentials. Security headers, rate limiting, dedicated security audit and `/docs` production policy are absent.

Two concrete remediation findings are included in G2:

- Replace client/global actor truth with a per-request authenticated principal.
- Correct Compose credential coupling where Neo4j currently reuses `MYSQL_PASSWORD`; use distinct `NEO4J_PASSWORD` without printing it.

## 3. Threat-driven controls

| Threat | CountyFlow example | Design response |
|---|---|---|
| Spoofing | forged `operator_id`, token, or anonymous task socket | validated JWT principal; server actor; one-time WS ticket |
| Tampering | dispatcher override or forced memory confirmation | permission gate plus unchanged business rules |
| Repudiation | denial of privileged attempt | durable security admission audit plus existing business audit |
| Disclosure | token/header/body/evidence/checkpoint in logs/API | central redactor, typed projections, safe errors, internal monitoring |
| DoS | dispatch/override/mutation/query/ticket floods | atomic per-principal Redis token buckets, input caps, bounded queries |
| Privilege elevation | hidden UI bypassed with direct POST | backend permission dependencies and direct-API tests |

The resource model is deliberately single organization. No region, tenant, owner, organization tree, or billing scope is invented.

## 4. Architecture alternatives

### A. AuthenticationProvider + OIDC/JWT + dev JWT + RBAC — selected

This gives CountyFlow one vendor-neutral principal and permission boundary, production asymmetric/public-key verification, real Docker-development role tests, and no extra container.

### B. Static API key — rejected

It is inadequate for per-user actor identity, role changes, revocation, and privileged-operation non-repudiation. A later service-account design may use an independently scoped credential but cannot replace human auth.

### C. Deploy Keycloak — deferred

It adds service/backup/upgrade/IAM scope and would expand the frozen 11 services. The provider interface remains compatible with Keycloak or another OIDC issuer later.

## 5. Authentication model

`AuthenticationProvider.authenticate(BearerCredentials)` returns immutable `AuthenticatedPrincipal(subject_id, display_name, roles, permissions, auth_method, issued_at, expires_at, jti)`. FastAPI owns reusable `get_current_principal` and `require_permission(...)` dependencies. Application services receive the principal or a server-built actor context and never parse a token.

Production requires an OIDC/JWT provider at startup. It validates exact issuer and audience, `sub/iat/nbf/exp/jti`, server allowlisted `RS256|ES256`, configured JWKS keys and `kid`, with 30-second clock skew. `alg=none`, client-broadened algorithms, unknown roles/permissions, and missing claims are rejected. Unknown `kid` triggers one bounded JWKS refresh. Access TTL target is ten minutes.

Docker-dev uses HS256 with an ignored ≥256-bit development secret, a maximum 15-minute token, explicit non-admin role selection, and a permanent `DEV AUTH` banner. `scripts/create-dev-token.ps1` will refuse production. There is no password database or committed token.

Production validation rejects `development_jwt`, `trusted`, missing provider, missing issuer/audience/JWKS, wildcard CORS, or an unsafe secret configuration. Auth-provider failure never admits a protected caller.

## 6. Token lifecycle and browser storage

The SPA holds the short-lived access token in `AuthContext` memory. `localStorage` and `sessionStorage` are rejected because XSS can read them; a CountyFlow HttpOnly session/refresh cookie is deferred because the current direct SPA/API architecture has no BFF session boundary and it would require CSRF/session work.

Production uses OIDC Authorization Code + PKCE with `state` and `nonce`; reload recovery re-enters the provider authorization/session boundary. CountyFlow does not persist refresh material. Docker-dev may require identity selection again after reload.

Logout/emergency revocation stores a digest of `jti` in Redis for the remaining token lifetime. Role removal takes effect within the short access TTL; incident response can revoke active JTIs. A persistent user token-version store is deferred.

## 7. RBAC and endpoint admission

Roles are exactly `DISPATCHER`, `SUPERVISOR`, `OPERATOR`, `AUDITOR`, and `ADMIN`. Permissions are exactly:

```text
dispatch:read, dispatch:create, dispatch:review,
orders:read, anomalies:read, agents:read,
memory:read, memory:mutate,
runtime:read, runtime:override,
audit:read, monitor:read, system:admin
```

The selected matrix is:

- Dispatcher: dispatch read/create and order/anomaly/agent/memory reads.
- Supervisor: Dispatcher plus review, runtime read/override, memory mutation, audit and monitoring reads.
- Operator: agent/runtime/audit/monitor reads only.
- Auditor: runtime/memory/audit/monitor reads only.
- Admin: every explicit permission plus `system:admin`.

Exact route mapping is centralized and contract-tested as documented in `docs/permissions.md`. Dispatch create/read, Runtime read/override, Memory read/mutate, Observability read, audit projections, and WS ticket issuance each have one named permission. Current product pages without backend APIs do not cause new business endpoints to be invented.

Runtime and Shared Memory request DTOs no longer own actor identity. Full override/memory actor/reason/evidence data is an `audit:read` projection; safe operational summaries remain available under their read permission. Raw checkpoint payloads remain prohibited for every role.

## 8. WebSocket security

Three approaches were compared:

- HttpOnly cookie: strong browser transport but requires a new CountyFlow session/CSRF boundary; deferred.
- One-time ticket: short-lived, scope-limited, no long-lived bearer in URL; selected.
- Access token query parameter: vulnerable to URL/proxy/access-log retention; rejected.

`POST /api/v1/ws-tickets` uses Bearer authentication, target permission/resource authorization, and `ws_ticket` rate limiting. It creates a 256-bit opaque ticket, stores only its digest in Redis, binds subject + exact task + permission, and expires in 45 seconds. WebSocket admission atomically consumes it once. Reconnect requires a new ticket. Codes `4401`, `4403`, and `4408` distinguish invalid, wrong-scope, and expired/replayed tickets without secret detail. Ticket query strings are never logged.

## 9. Rate limiting

One Redis Lua token-bucket adapter is hidden behind a protocol. Keys use a digest of subject plus an allowlisted operation class; authenticated quotas are never global or IP-only. Initial configurable refill/burst values are:

| Class | Refill | Burst |
|---|---:|---:|
| dispatch submit | 120/min | 30 |
| runtime override | 12/min | 3 |
| memory mutation | 30/min | 5 |
| observability read | 300/min | 60 |
| WS ticket | 60/min | 10 |
| invalid authentication supplement | 60/min per trusted network source | 10 |

Denial is 429 `RATE_LIMIT_EXCEEDED` with `Retry-After`. Exact same-principal/same-fingerprint idempotent replays can return the prior result before consuming another token; conflicts and new work are charged. High-risk writes and ticket/revocation operations fail closed if Redis is unavailable. Bounded reads may use a documented process-local emergency cap and explicit degraded signal. Redis restart resetting quota is accepted because quota is not business truth.

## 10. Security audit and data protection

Dedicated event types cover authentication failure, authorization denial, rate denial, override/memory denial, invalid/expired tokens, WS ticket rejection, and redaction. Allowed fields are bounded event/permission/route-template/status/reason/request/time plus known subject and trusted normalized network address in access-controlled audit. Tokens, cookies, headers, passwords, keys, bodies, raw exceptions and queries are forbidden.

High-risk write admission requires a durable authorization audit before business mutation. Audit failure never changes a deny to allow. Retention is 180 days by default, configurable 30–365, with bounded maintenance cleanup and no archive service.

Data classes are PUBLIC, INTERNAL, SENSITIVE, and SECRET. A recursive `SensitiveDataRedactor` handles nested fields, `SecretStr`, header/key names, bearer/JWT/basic patterns and credential URLs. Safe route-template middleware replaces raw URL access logs. DTOs are explicit and least-privilege.

Input/body policy adds a 2,000-character anomaly description, retains existing override/memory bounds, and applies pre-parse JSON caps: 64 KiB default, 16 KiB dispatch, 8 KiB override, 32 KiB memory mutation and 2 KiB ticket. File upload is not applicable.

## 11. HTTP/browser security

Production uses explicit HTTPS CORS origins, Bearer `Authorization`, credentials off, and no wildcard. With no CountyFlow ambient auth cookie, API CSRF exposure is low; the OIDC flow still requires PKCE/state/nonce. Any future cookie session must add Secure/HttpOnly/SameSite, Origin validation and CSRF token before enabling credentials.

Headers include `nosniff`, strict referrer policy, restrictive permissions policy, CSP with `frame-ancestors 'none'`, no `unsafe-eval`, and explicit application/OIDC connect sources. HSTS is emitted only for confirmed HTTPS production. Docker-dev gets only exact Vite/API/HMR relaxations. `/health` stays public and minimal; `/metrics`/Prometheus stay internal; production FastAPI docs are disabled; Grafana requires independent non-default credentials or future SSO.

## 12. Frontend design

`AuthContext` stores principal, roles, permissions, auth state and expiry. The shared client injects the memory token and performs a single terminal 401 transition: clear sensitive caches, abort protected queries, close sockets, stop retry loops and reauthenticate. 403 produces a distinct no-permission state.

Route/action guards implement the role UX while backend checks remain authoritative. Intervention, Memory mutation, Monitoring, and audit details each display their permission state. Monitoring API mode never falls back to Mock. Docker-dev visibly identifies development authentication.

## 13. Security observability

V2-G1 gains four controlled families:

```text
countyflow_authentication_failures_total{reason_code,route_class}
countyflow_authorization_denied_total{reason_code,route_class}
countyflow_rate_limit_exceeded_total{reason_code,route_class}
countyflow_ws_ticket_rejected_total{reason_code,route_class}
```

There are no subject/IP/task/token labels. Grafana adds a Security section. Alerts are AuthenticationFailureSpike, AuthorizationDeniedSpike, RuntimeOverrideDeniedSpike, RateLimitSpike, and WsTicketRejectionSpike, each with a minimum-traffic guard and `for` duration. Monitoring shows only aggregates to principals with `monitor:read`; individual audit events require `audit:read`.

## 14. Failure policy

- Invalid/missing/expired tokens: safe 401.
- Missing permission: safe 403 before service call.
- Rate denial: 429 with retry guidance.
- OIDC/JWKS unavailable: protected writes closed; no development fallback.
- Ticket/revocation/limiter Redis unavailable: high-risk admission closed.
- Audit unavailable: deny stays deny; high-risk admitted write stops before mutation.
- Prometheus/Grafana unavailable: business path unchanged.
- Browser expiry: sensitive state and network work stop; no 401 request storm.
- Error responses never expose stack traces, SQL, Redis keys, Cypher, token claims or provider payloads.

## 15. Test and acceptance model

TDD has Unit, API integration, real Redis, browser E2E, Docker E2E, security regression and performance comparison layers. It covers all 29 explicitly requested authentication/permission/ticket/rate/audit/redaction/CORS/header/body tests, a single role-matrix contract, direct API bypass, concurrent override abuse, metrics/alerts, secret scans, and production fail-closed configuration.

Real browser scenarios use each of five signed development roles. Real Redis proves atomic ticket consumption/expiry/scope, bucket concurrency/per-principal isolation, revocation TTL and acceptable restart reset. Docker remains 11 services and uses signed development JWTs rather than automatic admin.

Security-enabled normal traffic must retain QPS `>=200`, P95 `<300 ms`, and unexpected error rate `<0.1%`. Load configuration can explicitly raise test quotas but cannot disable authentication/rate limiting, and before/after artifacts disclose settings.

## 16. Delivery documents

- `docs/security_spec.md` — normative architecture, threats and policies.
- `docs/permissions.md` — exact role and endpoint matrices.
- `docs/security-runbook.md` — token, denial, rate, ticket, rotation and incident operations.
- This design — decision record and scope.
- `docs/superpowers/plans/2026-08-28-v2-g2-security-hardening.md` — TDD execution sequence.

## 17. Deferred scope

Keycloak/Auth0/provider deployment selection, enterprise SSO management, registration/password/SMS/recovery, SCIM, organization tree, multi-tenancy, billing, Vault, WAF, SIEM, IDS/IPS, Kubernetes NetworkPolicy, password database, security archive service, and new business APIs are explicitly deferred.

## 18. Design self-review

- Operator spoofing is blocked by server-derived actor identity.
- WebSocket is never anonymous and never receives a bearer token in its URL.
- Production cannot start/fall back with development/trusted auth.
- Dispatcher/Operator/Auditor cannot override; only Supervisor/Admin may attempt it.
- Backend permission checks remain authoritative when UI controls are bypassed.
- Rate limits are per subject, not solely IP.
- Tokens and secrets are centrally redacted and absent from metrics/audit/artifacts.
- Grafana is authenticated and Prometheus remains internal.
- Docker stays at 11 services.
- No production implementation or business algorithm change is included in this design turn.
