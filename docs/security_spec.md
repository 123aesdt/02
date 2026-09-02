# CountyFlow V2-G2 Security Specification

**Status:** IMPLEMENTED AND VERIFIED — V2-G2 acceptance closed on 2026-08-29

**Date:** 2026-08-28

**Scope:** Authentication, authorization, single-organization RBAC, resource admission, WebSocket tickets, Redis rate limiting, security audit, sensitive-data handling, browser security, and security verification.

## 1. Security invariants

1. Authentication establishes who the caller is; authorization establishes whether that principal may attempt an operation; existing business policy still decides whether the attempt is valid.
2. Actor identity is server-derived from `AuthenticatedPrincipal`. An `operator_id`, role, or permission supplied by a request body is never security truth.
3. `runtime:override` does not bypass `expected_version`, stable-boundary, old-value, next-node, allowlist, idempotency, or checkpoint-promotion rules.
4. `memory:mutate` does not make `human_confirmed=true` an authorization mechanism.
5. Production never falls back to development identity, a trusted authorizer, or Mock data.
6. Protected writes fail closed when authentication, authorization, ticket, revocation, or rate-limit controls required for admission are unavailable.
7. Access tokens, cookies, passwords, signing keys, API keys, Authorization headers, and full request bodies never enter logs, audit records, metrics, browser URLs, or API error responses.
8. Frontend guards improve UX only. Every protected HTTP and WebSocket operation is revalidated by the backend.
9. MySQL remains business truth; Redis security state is ephemeral control state; no security work changes the 8-Agent graph or business decision algorithms.

## 2. Existing security audit

The audit reflects the repository at the V2-G1 frozen baseline.

| Area | Existing evidence | Finding / V2-G2 boundary |
|---|---|---|
| Unified authentication | No `AuthenticationProvider`, bearer dependency, principal, JWT/session/API-key flow, or `/auth/me` | Missing; introduce one provider boundary |
| Runtime authorization | `TrustedRuntimeThreadAuthorizer` and `DisabledRuntimeThreadAuthorizer`; production can require an injected external adapter | Useful fail-closed precedent, but trusted identity is process-global and not request-authenticated |
| Runtime actor | Override service builds the command and takes actor from the authorizer | Good boundary; replace global trusted context with request principal without weakening business validation |
| Observability authorization | Separate trusted/disabled `ObservabilityAuthorizer` requiring `monitor:read` | Fragmented, requestless identity; converge on the unified principal dependency |
| Shared Memory authorization | API directly calls mutation service; request DTO contains `operator_id` and `human_confirmed` | Critical gap: authenticate, require `memory:mutate`, and overwrite actor from the principal |
| Dispatch API | Create/status/result routes have no auth dependency | Require `dispatch:create` or `dispatch:read` |
| Task WebSocket | Connection is accepted after task existence only | Anonymous data path; replace with one-time ticket admission |
| Frontend auth | No AuthContext/principal store/token lifecycle/route guard; fetch and WebSocket clients send no credentials | Add memory-held access token and permission-aware UX |
| CORS | Explicit configured origins, credentials disabled, GET/POST/OPTIONS allowlist | Preserve; reject wildcard origins in production and allow `Authorization` header |
| Security headers | No central response-header middleware | Add profile-aware headers and production CSP/HSTS policy |
| Rate limiting | None | Add Redis atomic token buckets; no new service |
| Security audit | Business audit and safe IDs exist; no dedicated authentication/authorization/rate-limit event model | Add separate event types on shared durable audit infrastructure |
| Logging redaction | JSON formatter redacts sensitive *field names* and `SecretStr`; Shared Memory has limited text regexes | Extend to recursive structural/value redaction and ensure access logs do not expose ticket queries |
| DTO minimization | Typed DTOs are used; checkpoint payload is not returned | Preserve; restrict full override/memory operator evidence to `audit:read` |
| Metrics | V2-G1 low-cardinality catalog exists | Add four controlled security families; never label by subject/IP/task |
| Prometheus | Internal Docker network, no host port | Correct; keep browser and public network access prohibited |
| Grafana | Host port with environment-required admin credentials; sign-up disabled | No `admin/admin`, no anonymous access; production needs independent credential or future SSO |
| Docs | FastAPI defaults are active | docker-dev only; production disables docs/OpenAPI/Redoc |
| Secrets | `.env`, `.env.*`, `.docker.env`, `.secrets`, key files ignored; examples have empty secrets | Preserve and add explicit rotation boundaries |
| Credential isolation | Compose maps Neo4j auth/password from `MYSQL_PASSWORD` although `NEO4J_PASSWORD` is declared in `.env.example` | Defect to fix in implementation: Neo4j must use its own secret |
| Input bounds | Many IDs/reasons/evidence values are bounded; Shared Memory canonical body is bounded | Add anomaly description bound and global/route body caps |
| File upload | No upload API exists | NOT APPLICABLE; do not add one |

## 3. Threat model

| STRIDE | Concrete CountyFlow threat | Affected path | Control |
|---|---|---|---|
| Spoofing | Caller submits another `operator_id` to mutate memory or claims supervisor identity | `POST /memory/mutations`, override actor | JWT validation; server-derived principal; ignore/remove client actor |
| Spoofing | Stolen/forged/expired/wrong-audience token | All protected HTTP endpoints | issuer/audience/time/algorithm validation, short TTL, `jti` revocation |
| Spoofing | Anonymous browser guesses task ID and opens event stream | Task WebSocket | authenticated ticket issuance, scope binding, atomic single-use consumption |
| Tampering | Dispatcher changes runtime state despite not being a supervisor | Runtime override | `runtime:override` dependency plus unchanged Runtime Override policy |
| Tampering | Client uses `human_confirmed=true` to force a memory write | Shared Memory | `memory:mutate` before business policy; human confirmation remains business evidence only |
| Tampering | Replay of override/mutation/ticket | Runtime, Memory, WebSocket | existing idempotency/preconditions; one-time ticket; short JWT TTL and optional revocation |
| Repudiation | Operator denies a rejected or successful privileged attempt | Override, mutation, admin/security routes | durable security admission event plus existing business audit with principal actor/request ID |
| Information disclosure | Authorization header, ticket, DB URL, Cypher, body, or credential reaches logs/errors | Middleware/providers/errors | recursive redactor, route-template logging, normalized errors, query redaction |
| Information disclosure | `dispatch:read` exposes operator/reason/evidence intended for auditors | Result/history DTOs | field-level projections; `audit:read` for full actor/evidence detail |
| Information disclosure | Prometheus/Grafana or checkpoint payload exposed to browser/public | Monitoring/runtime | internal Prometheus; authenticated Grafana; typed read API; no raw checkpoint |
| Denial of service | Flood dispatch, override, mutation, monitoring, ticket issuance, or invalid auth | API/Redis/Worker | per-principal token buckets, supplemental network signal, payload caps, bounded queries |
| Denial of service | Large anomaly/evidence JSON amplifies parsing/logging/storage | FastAPI DTOs | pre-parse body cap and field/canonical JSON bounds |
| Elevation of privilege | UI hides a button but direct API call succeeds | All writes | backend `require_permission`; direct-bypass tests |
| Elevation of privilege | Production starts with trusted development identity | Application bootstrap | production configuration validator fails startup; dev provider rejects production profile |

Trust boundaries are browser↔FastAPI, FastAPI↔OIDC/JWKS, FastAPI↔Redis security controls, FastAPI↔MySQL audit/business data, internal Prometheus/Grafana, and Worker/provider egress. The first release is a single-organization RBAC model: there is no invented tenant, region, or owner hierarchy.

## 4. Architecture decision

### Option A — provider abstraction + OIDC/JWT + development JWT + RBAC (selected)

```text
OIDC / signed dev issuer
          │ Bearer access token
          ▼
AuthenticationProvider → AuthenticatedPrincipal
          │
          ├─ require_permission(...)
          ├─ resource authorizer (single organization)
          ├─ rate-limit admission
          ├─ security audit
          └─ existing application service/business policy
```

It separates vendor validation from application roles, supports production public-key verification, preserves FastAPI dependency injection, and keeps Docker at 11 services.

### Option B — static API key (rejected as final architecture)

An API key can authenticate a machine, but provides weak per-user identity, coarse revocation, poor role-change behavior, and inadequate non-repudiation for override and memory mutation. It may be considered later for a separately scoped service account, never as the human management plane.

### Option C — deploy Keycloak now (deferred)

Keycloak could supply a full IAM service, but would add a twelfth service, operational ownership, backup/upgrade requirements, and features outside this hardening phase. Production uses an OIDC-compatible provider boundary without selecting or deploying a vendor here.

## 5. Authentication contracts

The application-owned value object is immutable and JSON-free at request boundaries:

```python
@dataclass(frozen=True)
class AuthenticatedPrincipal:
    subject_id: str
    display_name: str
    roles: frozenset[Role]
    permissions: frozenset[Permission]
    auth_method: AuthMethod
    issued_at: datetime
    expires_at: datetime
    jti: str

class AuthenticationProvider(Protocol):
    async def authenticate(self, credentials: BearerCredentials) -> AuthenticatedPrincipal: ...
```

`get_current_principal` extracts exactly one Bearer credential, calls the provider, and maps failures to stable 401 codes without token detail. `require_permission(Permission.RUNTIME_OVERRIDE)` is a reusable dependency factory. Application services receive the principal or a narrow server-built actor/security context; they do not parse HTTP headers or vendor claims.

Recommended read endpoints are `GET /api/v1/auth/me` and authenticated `POST /api/v1/auth/logout`. CountyFlow does not add password login, registration, recovery, SMS, or a user database.

### Production provider

- OIDC/JWT-compatible, using issuer discovery/JWKS or explicitly configured public keys.
- `RUNTIME_PROFILE=production` requires `AUTHENTICATION_PROVIDER=oidc_jwt` and complete issuer/audience/JWKS configuration. `development_jwt`, `trusted`, missing, or invalid configuration fails startup.
- Provider/JWKS failure rejects protected admission with `503 AUTHENTICATION_UNAVAILABLE`; it never yields an anonymous/admin principal.
- Principal roles/permissions are derived through a server-owned allowlisted claim mapper. Unknown roles and permissions are ignored and audited, not accepted dynamically.

### Docker-development provider

- `development_jwt` is allowed only in `local`, `test`, and `docker-dev` profiles.
- JWTs are signed with an ignored environment secret of at least 256 bits. No default secret is committed.
- The docker-dev frontend starts a bounded short-lived `ADMIN` development session automatically; the removed manual token input is not rendered.
- `scripts/create-dev-token.ps1` remains a role-explicit security-test helper and refuses a production profile. At least one non-admin fixture exists for every approved role.
- The app displays a permanent development-identity banner without exposing the underlying access token.
- Requests are not auto-admin. A real signed token is still required.

## 6. JWT validation and lifecycle

Required claims are `iss`, `aud`, `sub`, `iat`, `nbf`, `exp`, and `jti`. `display_name` and allowlisted roles may be mapped from configured claims.

- Production algorithms: `RS256` or `ES256` only, selected by server configuration. The header `alg` cannot broaden the allowlist; `none` is always rejected.
- Docker-development algorithm: `HS256` only with the ignored development secret.
- Access-token TTL target: 10 minutes production, at most 15 minutes docker-dev.
- Clock skew/leeway: 30 seconds for `nbf`, `iat`, and `exp` validation.
- Audience and exact normalized issuer are mandatory.
- `kid` selects an allowlisted JWKS key. Unknown `kid` triggers one bounded cache refresh, then rejects.
- OIDC public-key rotation uses overlapping old/new keys and bounded JWKS caching. CountyFlow never holds a production private signing key when an external issuer is used.
- Logout/emergency revocation stores `countyflow:auth:revoked:{sha256(jti)}` with TTL equal to the remaining token lifetime. The raw token and raw `jti` are not Redis key text.
- Role removal becomes effective no later than the access-token TTL. High-risk incident response may revoke current JTIs immediately. A persistent token-version/user directory is deferred because CountyFlow does not own user records.

## 7. Browser token decision

The selected SPA approach is a short-lived Bearer access token held in memory by `AuthContext`.

| Storage | Benefit | Risk / decision |
|---|---|---|
| `localStorage` | Survives restart | Any successful XSS can read a long-lived token; rejected |
| `sessionStorage` | Scoped to tab | Still readable by XSS; not the default |
| In-memory | Not persisted or directly readable after reload | Reload requires safe reauthentication; selected |
| CountyFlow HttpOnly cookie | Hidden from JavaScript | Requires a backend session/refresh system and CSRF controls; deferred unless a future BFF is approved |

Production reload recovery uses the external OIDC Authorization Code + PKCE flow and the provider's own authenticated session/silent authorization boundary. CountyFlow stores neither a refresh token nor a permanent access token in web storage. OIDC `state`, `nonce`, and PKCE are mandatory. Docker-dev may require selecting a development identity again after reload; convenience does not justify persistent admin tokens.

## 8. Authorization and resource boundary

The canonical roles and permissions are defined in `docs/permissions.md`. Permission dependencies run after authentication and before rate-limit/business admission. Resource authorizers consume the principal plus canonical resource metadata loaded server-side.

V2-G2 is single organization. A principal with an approved read permission can read all resources in the current deployment. Region, organization, owner, tenant, and billing scopes are explicitly not invented. A future multi-organization change must extend the principal and resource repository together and undergo a new threat review.

Resource IDs from the path are selectors, never proof of authorization. Unknown or unauthorized resources use normalized 404/403 policy without exposing internal checkpoint, Redis, database, or graph details.

### Runtime Override

- HTTP admission requires `runtime:override`.
- Actor ID, display role, and permission snapshot are built from the principal.
- Any body `operator_id`, role, or permissions field is removed or ignored and rejected as an extra field at the DTO boundary.
- Existing allowlisted `Vehicle.status`, stable-boundary, version, old-value, next-node, idempotency, lock, and checkpoint rules remain unchanged.

### Shared Memory

- POST mutation requires `memory:mutate`; facts and mutation reads require `memory:read`.
- Client `operator_id` is removed/rejected; service command actor is supplied separately from the principal.
- `human_confirmed` is a policy fact only and never grants permission.
- Full operator/source/evidence fields require `audit:read`; ordinary memory read receives a minimized projection.

### Runtime, audit, and monitoring

- Runtime thread/checkpoint projections require `runtime:read`; raw checkpoint state is never returned.
- Existing dispatch audit summary may remain under `dispatch:read`, but full actor, override reason, memory evidence, and security events require `audit:read`.
- Observability read API requires `monitor:read`; browsers never receive PromQL or Prometheus credentials.
- Grafana has its own authenticated operator boundary. Frontend `monitor:read` does not make a public/anonymous Grafana acceptable.

## 9. WebSocket ticket protocol

Browser WebSocket cannot reliably attach an Authorization header. Long-lived bearer tokens in URLs are rejected because proxies, browser history, and access logs can retain them. Cookie auth would introduce a CountyFlow session and CSRF boundary. The selected mechanism is a one-time ticket.

1. Browser calls `POST /api/v1/ws-tickets` with its Bearer token and `{target_type: "task", target_id}`.
2. Backend authenticates, requires `dispatch:read`, checks target existence/resource access, and applies the `ws_ticket` limiter.
3. Backend generates a cryptographically random 256-bit opaque value and stores only a digest in Redis with principal subject, fixed scope, required permission, issue/expiry timestamps, and TTL 45 seconds.
4. Browser connects to `wss://.../api/v1/ws/tasks/{task_id}?ticket=<opaque>&last_event_id=...`.
5. Backend atomically validates and consumes the digest with Lua/`GETDEL`, verifies exact task scope and permission snapshot, accepts once, and deletes state.
6. Ticket query values are redacted before access logging. The access token never enters the WebSocket URL.

Close codes are stable: `4401` missing/invalid authentication ticket, `4403` wrong scope/permission, and `4408` expired/replayed ticket. Reconnect obtains a fresh ticket; it does not reuse the old one. Ticket issuance fails closed when Redis is unavailable.

## 10. Redis rate limiting

An application-owned `RateLimiter` protocol hides Redis. The concrete implementation uses an atomic Lua token bucket. Key format is:

```text
countyflow:ratelimit:{sha256(subject_id)[0:32]}:{operation_class}
```

Authenticated limits use subject identity, not IP. A normalized trusted-proxy remote address is retained only as supplemental audit/input for an `authentication_invalid` abuse bucket; it never makes all users behind NAT share application limits.

Initial defaults are deliberately configurable and are validated against the existing QPS acceptance rather than claimed as final capacity:

| Operation class | Refill | Burst | Risk |
|---|---:|---:|---|
| `dispatch_submit` | 120/min | 30 | worker/queue admission |
| `runtime_override` | 12/min | 3 | highest-risk state mutation |
| `memory_mutation` | 30/min | 5 | durable/control-plane mutation |
| `observability_read` | 300/min | 60 | bounded read queries |
| `ws_ticket` | 60/min | 10 | connection churn |
| `authentication_invalid` | 60/min per normalized network source | 10 | unauthenticated brute force supplement |

Every denial is `429` with `RATE_LIMIT_EXCEEDED`, `Retry-After`, and optional consistent `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`. No Redis key or Lua detail is returned.

Admission order is authenticate → exact idempotent replay lookup → rate-limit reservation → business validation/transaction. An exact replay owned by the same principal with the same payload fingerprint may return the prior response without consuming a new operation token; conflicting or unknown idempotency keys are charged and continue to normal conflict handling. This prevents network retries from self-locking while preventing arbitrary keys from bypassing limits.

Redis restart may reset buckets; rate-limit state is not business truth. Failure policy:

- Runtime override, memory mutation, dispatch submit, ticket issuance, logout/revocation writes: fail closed with `503 SECURITY_CONTROL_UNAVAILABLE`.
- Bounded observability and ordinary protected reads: use a small process-local emergency limiter and return a degraded response when safe; never silently create unlimited write admission.
- `/health`: remains public and minimal without rate-limit dependency details.

## 11. Security audit

Security audit and business audit may share persistence infrastructure, but use separate event types and schemas.

Events:

```text
AUTHENTICATION_FAILED, AUTHORIZATION_DENIED, RATE_LIMIT_EXCEEDED,
RUNTIME_OVERRIDE_DENIED, MEMORY_MUTATION_DENIED,
TOKEN_INVALID, TOKEN_EXPIRED, WS_TICKET_REJECTED,
SENSITIVE_DATA_REDACTED
```

Allowed fields are `subject_id` when known, `event_type`, `permission`, normalized `route_template`, `status`, bounded `reason_code`, `request_id`, UTC timestamp, and normalized remote address when trusted. Raw exception text, token/JTI, cookie, authorization header, password, API key, body, evidence, Cypher/SQL, and provider response are prohibited.

High-risk write admission records an authorization decision durably before the business mutation proceeds; if that audit admission write cannot be persisted, the high-risk operation fails closed. Denied/invalid attempts remain denied even if audit persistence is unavailable; they emit a bounded safe log and metric so audit failure can be detected. Existing successful override/memory business records continue to be authoritative for the result.

Retention is 180 days by default, configurable from 30–365 days. V2-G2 supplies a bounded runbook cleanup command/job boundary, not an archive service. Security audit is append-only to application roles; only system maintenance can expire records under retention policy.

## 12. Sensitive-data policy and redaction

| Class | Examples | Handling |
|---|---|---|
| PUBLIC | application version, public generic health state | May be anonymous if explicitly approved |
| INTERNAL | task/thread/mutation/checkpoint IDs, route templates, topology | Authenticated use; logs only when needed; never metric labels |
| SENSITIVE | driver name, vehicle details, route facts, anomaly description, override reason, memory/audit evidence | Least-privilege DTO, bounded audit/log use, no public responses |
| SECRET | API/JWT keys, token, cookie, password, Authorization header, database URL credentials | Environment/orchestrator secret only; always redact; never persist in artifacts |

`SensitiveDataRedactor` is a central recursive component used by structured logging, audit field construction, normalized exception handling, and test artifact scans. It redacts case-insensitive sensitive keys, `SecretStr`, Bearer/JWT/basic-auth patterns, credential-bearing URLs, cookies, and nested mapping/list values; it also applies maximum safe lengths. Redaction emits only a bounded counter/reason, never the original secret.

Uvicorn access logs must use route templates or be disabled in favor of the safe request middleware. Ticket/query strings and raw URLs are never formatted. Error responses expose stable codes and safe messages only; no stack trace, SQL, Redis key, Neo4j query, authorization claim, or vendor payload.

## 13. DTO and input minimization

- Response models are explicit; ORM/driver/session/checkpoint objects are never automatically serialized.
- Runtime DTOs expose only page-required state summary, version, next node, and safe intervention fields.
- `runtime:read` history uses an operational projection; `audit:read` is required for operator identity and full reason/evidence.
- Memory read uses safe canonical/projection status; mutation actor/evidence is an audit projection.
- Observability exposes only fixed query DTOs and bounded security aggregates, never subjects or raw events.
- `anomaly_description` gains a 2,000-character bound. Existing override reason (512), memory evidence (2,000), and value/proposed JSON (16/32 KiB) remain.
- Pre-parse body caps: default JSON 64 KiB; dispatch 16 KiB; override 8 KiB; memory mutation 32 KiB; WS ticket 2 KiB. Excess is `413 PAYLOAD_TOO_LARGE`.
- All future search input must be bounded to 256 characters and server-owned query templates. No current search endpoint is added.
- File upload is NOT APPLICABLE.

## 14. Browser and HTTP security

### Headers

All profiles send `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, and a restrictive `Permissions-Policy` disabling camera, microphone, geolocation, payment, and USB. CSP includes `default-src 'self'`, `base-uri 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, and `form-action 'self'`.

Production CSP uses self-hosted scripts/styles/assets, no `unsafe-eval`, and an explicit `connect-src` for the CountyFlow HTTPS/WSS origin and approved OIDC issuer. HSTS is emitted only when the deployment is actually HTTPS and `SECURITY_HSTS_ENABLED=true`; proxy trust is explicit. Docker-dev adds only the exact Vite/API/HMR HTTP/WS origins needed for development and never relaxes production policy.

### CORS and CSRF

- Production origins are explicit HTTPS origins; `*` is rejected at configuration validation.
- Bearer APIs keep `allow_credentials=false` and add only `Authorization`, `Content-Type`, and `X-Request-ID` to allowed headers.
- The selected architecture has no CountyFlow ambient auth cookie, so conventional CSRF does not authorize API actions.
- OIDC authorization uses `state`, `nonce`, and PKCE. If a future HttpOnly refresh/session cookie is approved, it must use `Secure`, `HttpOnly`, `SameSite=Lax/Strict`, Origin validation, and a CSRF token before credentials are enabled.

### Health, metrics, docs, and Grafana

- Anonymous `/health` returns only service/version/ready-style status and no dependency endpoints, configuration, credentials, or exception details.
- `/metrics` and Prometheus stay internal and are never a frontend dependency.
- FastAPI docs/OpenAPI/Redoc are enabled in docker-dev and disabled by default in production.
- Grafana disables anonymous/admin-default access; docker-dev uses environment-provided development credentials, production uses independent rotated credentials or a future SSO integration.

## 15. Frontend security UX

`AuthContext` owns `currentPrincipal`, roles, permissions, status (`LOADING`, `AUTHENTICATED`, `UNAUTHENTICATED`, `EXPIRED`), access-token expiry, login/reauth/logout actions, and abort/cancellation for protected queries. The shared API client attaches the in-memory Bearer token and handles one 401 transition; it clears sensitive query caches, closes sockets, stops retries, and shows session-expired reauthentication. It must not create a 401 retry storm.

Route guards prevent navigation to unauthorized workspaces; action guards hide or disable dangerous actions with an explicit reason. The backend remains authoritative.

- Dispatcher can submit/read dispatch but cannot override.
- Supervisor can override after all existing confirmations and preconditions.
- Auditor can inspect audit projections but cannot write dispatch/memory/runtime.
- Operator can view monitoring/runtime but cannot mutate memory or override.
- Admin can perform all approved operations.
- No `runtime:override`: intervention control is disabled/hidden and direct POST remains 403.
- No `monitor:read`: Monitoring shows `NO_PERMISSION`, never Mock fallback.
- `memory:read` without `memory:mutate`: read-only Memory UI.
- No `audit:read`: operator/reason/evidence details are omitted or visibly restricted.
- docker-dev shows a persistent automatic-development-identity banner and active role, with no manual token form.

## 16. Security metrics and alerts

The four new low-cardinality counters are:

```text
countyflow_authentication_failures_total{reason_code,route_class}
countyflow_authorization_denied_total{reason_code,route_class}
countyflow_rate_limit_exceeded_total{reason_code,route_class}
countyflow_ws_ticket_rejected_total{reason_code,route_class}
```

`reason_code` and `route_class` are finite enums. Subject, IP, token, task/thread, raw route, and message are forbidden labels. Security dashboards aggregate failures, denials, throttles, and ticket rejects only; they never expose tokens or individual principals.

Prometheus rules add `AuthenticationFailureSpike`, `AuthorizationDeniedSpike`, `RuntimeOverrideDeniedSpike`, `RateLimitSpike`, and `WsTicketRejectionSpike`. Each rule combines a time-window threshold with a minimum request/event-volume guard and a `for` duration to avoid alerts on isolated expected denials. Exact thresholds are calibrated during TDD/Docker testing and documented with runbook links.

## 17. Failure modes

| Failure | Required behavior |
|---|---|
| Missing/malformed/expired/wrong issuer or audience token | 401 with stable safe code; audit/metric; no provider detail |
| Auth provider/JWKS unavailable | Protected write fails closed; no dev fallback; bounded 503 |
| Permission missing | 403; no business service call; safe audit |
| Resource unavailable/not visible | normalized 404/403 policy; no existence leak beyond single-org contract |
| Redis ticket unavailable | Ticket issuance/connection fails closed |
| Redis rate limiter unavailable | High-risk writes fail closed; bounded reads use explicit degraded local cap |
| Security audit unavailable | Denied request stays denied; high-risk admitted write fails closed before mutation |
| Revocation store unavailable | Protected write fails closed; safe read policy is explicitly configured, never implicit |
| Token expires in browser | Clear sensitive state, stop queries/sockets/retries, reauthenticate |
| Grafana down | Product Monitoring continues from protected read API |
| Prometheus down | Monitoring unavailable/degraded; dispatch/runtime business path continues |
| Redactor fails | Drop unsafe field/value and emit safe metric; never log the unredacted fallback |

## 18. Secrets and rotation boundaries

- `.env`, `.docker.env`, `.env.*`, `.secrets/`, `*.pem`, and `*.key` remain ignored. Examples contain names and empty values only.
- Embedding, MySQL, Neo4j, Redis, Grafana, and development JWT secrets are independent. The current Neo4j/MySQL password coupling is removed during implementation.
- Production obtains secrets from deployment/orchestration secret injection or an external secret manager in a later platform phase; V2-G2 does not deploy Vault.
- Embedding/MySQL/Neo4j/Redis/Grafana credential rotation is environment replacement plus controlled restart and dependency verification. Where a server supports overlapping credentials, rotate server first, then clients, then retire old material.
- OIDC/JWT verification rotation is via JWKS `kid` overlap/cache refresh. Development signing-secret rotation invalidates all development tokens and restarts backend.
- Rotation validation checks functionality and secret-artifact scan without printing any value, prefix, suffix, length, or header.

## 19. Verification strategy

TDD proceeds Unit → API integration → real Redis → browser E2E → Docker E2E → security/performance regression. Required tests include every named test in the V2-G2 request, the role matrix contract, redaction recursion, direct API bypass, concurrent override abuse, security metrics, alert rules, production config validation, and secret scans.

Real Redis tests prove atomic ticket single-use, expiry, wrong scope, per-principal isolation, bucket concurrency, revoked-JTI TTL, and documented restart reset. Browser tests use signed development JWTs for all five roles, verify 401 versus 403 UX, ensure expiry stops background requests, and prove API mode never falls back to Mock. Docker remains 11 services.

Performance comparison is security OFF versus ON under otherwise identical normal authenticated traffic. Security-enabled acceptance remains QPS `>=200`, API P95 `<300 ms`, and unexpected error rate `<0.1%`; legitimate 401/403/429 scenarios are measured separately from the normal-flow error gate. Test-only thresholds may be raised by explicit configuration for load generation, never by disabling authentication or rate limiting, and results must disclose that configuration.

## 20. Explicitly deferred

Keycloak deployment, Auth0/Azure AD/Okta selection, complete enterprise SSO, registration, password database, SMS, password recovery, SCIM, organization tree, multi-tenancy, billing, Vault deployment, WAF, SIEM, IDS/IPS, Kubernetes NetworkPolicy, service mesh, and a security-event archive service are outside V2-G2.

## 21. Self-review

- Client actor spoofing: impossible by contract; server principal overwrites/removes body identity.
- Anonymous WebSocket: prohibited; one-time scoped ticket required.
- Production dev-auth fallback: configuration-invalid and startup-failing.
- Dispatcher override: denied by the role matrix and backend dependency.
- UI-only enforcement: prohibited; direct API tests required.
- IP-only limiting: prohibited for authenticated operations.
- Token in logs/URLs: access token prohibited; ticket query is redacted and single-use.
- Anonymous Grafana admin: prohibited.
- Public Prometheus: prohibited.
- Source-controlled API/JWT/private keys: prohibited.

## 22. Implemented verification

The V2-G1 baseline authorizers described in section 2 are historical audit evidence only. The current runtime has one request-scoped `AuthenticatedPrincipal` flow: HTTP and WebSocket admission authenticate first, permission dependencies authorize second, and Runtime Thread, Runtime Override, Observability, Shared Memory, Dispatch, and Security Audit services receive the authenticated principal explicitly. Process-global trusted/disabled authorizer switches and their runtime configuration branches have been removed.

Verified current behavior:

- five-role RBAC and direct API bypass denial passed in a real Docker runtime;
- task WebSocket admission requires a scoped, expiring, atomic single-use Redis ticket;
- actor identity for Runtime Override and Shared Memory is server-derived;
- Redis token-bucket admission, revocation, 401/403/429 behavior, security audit, safe errors, headers, CORS, and production fail-closed validation passed focused tests;
- the seven authenticated V2-E browser regressions passed without changing Routing, Graph Memory, Shared Memory, Checkpoint, or Runtime Override business semantics;
- authenticated security-ON performance passed with 16,575 requests, QPS 278.998, P95 270 ms, and 0% unexpected errors;
- the 11-service Compose topology is preserved, with nine backend/runtime services healthy, migration exiting 0, and the separately served Vite frontend remaining available;
- `.env` and `.docker.env` are ignored and the final secret-artifact scan returned 0 findings.

The machine-readable performance evidence is `docs/verification/v2-g2/raw/v2-g2-security-performance.json`; authenticated browser evidence is `docs/verification/v2-g2/raw/browser-authenticated-regression.json`. The final evidence matrix is `docs/verification/v2-g2/v2-g2-final-acceptance.md`.
