# CountyFlow V2-G2 Roles and Permissions

**Status:** DESIGN READY

**Authorization model:** single-organization RBAC with server-side resource admission

**Source of identity:** `AuthenticatedPrincipal`, never request body fields

## 1. Canonical permissions

| Permission | Allows an authenticated principal to attempt |
|---|---|
| `dispatch:read` | Read dispatch task status/result and subscribe to its safe task events |
| `dispatch:create` | Submit a new asynchronous dispatch task |
| `dispatch:review` | Perform a business review action when such an existing action is exposed; it does not grant runtime override |
| `orders:read` | Read order product views when backed by an API |
| `anomalies:read` | Read anomaly product views when backed by an API |
| `agents:read` | Read safe agent execution/product views |
| `memory:read` | Read minimized Vector/Graph/Shared Memory views |
| `memory:mutate` | Attempt a Shared Memory mutation, subject to all mutation policy and concurrency rules |
| `runtime:read` | Read minimized runtime thread, checkpoint metadata, and intervention eligibility |
| `runtime:override` | Attempt an allowlisted Runtime Override, subject to all V2-D1 rules |
| `audit:read` | Read full approved business/security audit projections and actor/reason/evidence detail |
| `monitor:read` | Read the bounded Observability API and security health summary |
| `system:admin` | Perform future explicitly mapped system administration; it is not a wildcard bypass in endpoint code |

Permission strings are a closed enum. Unknown token claims are ignored and audited. `system:admin` is assigned only to `ADMIN`; the `ADMIN` role also receives every concrete permission so application code does not rely on implicit wildcard behavior.

## 2. Role-to-permission matrix

| Permission | DISPATCHER | SUPERVISOR | OPERATOR | AUDITOR | ADMIN |
|---|:---:|:---:|:---:|:---:|:---:|
| `dispatch:read` | ✓ | ✓ | — | — | ✓ |
| `dispatch:create` | ✓ | ✓ | — | — | ✓ |
| `dispatch:review` | — | ✓ | — | — | ✓ |
| `orders:read` | ✓ | ✓ | — | — | ✓ |
| `anomalies:read` | ✓ | ✓ | — | — | ✓ |
| `agents:read` | ✓ | ✓ | ✓ | — | ✓ |
| `memory:read` | ✓ | ✓ | — | ✓ | ✓ |
| `memory:mutate` | — | ✓ | — | — | ✓ |
| `runtime:read` | — | ✓ | ✓ | ✓ | ✓ |
| `runtime:override` | — | ✓ | — | — | ✓ |
| `audit:read` | — | ✓ | ✓ | ✓ | ✓ |
| `monitor:read` | — | ✓ | ✓ | ✓ | ✓ |
| `system:admin` | — | — | — | — | ✓ |

Rationale:

- `DISPATCHER` owns normal dispatch intake and operational business reads, not control-plane writes.
- `SUPERVISOR` is the smallest role permitted to review, mutate approved memory, and override a stable runtime boundary. It also has audit/monitor visibility needed to make and investigate those decisions.
- `OPERATOR` is an operations/monitoring role. It can see safe agent/runtime status and audit evidence but cannot submit dispatch, mutate memory, or override runtime state.
- `AUDITOR` is read-only across audit, runtime, memory, and monitoring evidence.
- `ADMIN` has the explicit union of all current permissions plus `system:admin`.

No role grants permission to alter audit records. No role bypasses idempotency, version, allowlist, stable-boundary, projection, or business review rules.

## 3. Existing endpoint mapping

| Method / endpoint | Required permission | Resource/field rule | Rate-limit class |
|---|---|---|---|
| `GET /health` | Public | Minimal service readiness only | public health guard |
| `GET /docs`, `/openapi.json`, `/redoc` | docker-dev only | Disabled in production | N/A |
| `GET /api/v1/auth/me` | Authenticated | Own principal only; no token claims/raw token | general read |
| `POST /api/v1/auth/logout` | Authenticated | Revoke caller `jti` only | auth control |
| `POST /api/v1/dispatch-tasks` | `dispatch:create` | Principal is attached to admission/audit; existing idempotency remains | `dispatch_submit` |
| `GET /api/v1/dispatch-tasks/{task_id}` | `dispatch:read` | Single-organization task access; safe status DTO | general read |
| `GET /api/v1/dispatch-tasks/{task_id}/result` | `dispatch:read` | Safe dispatch/audit summary only | general read |
| `POST /api/v1/ws-tickets` | Target-dependent; task ticket requires `dispatch:read` | Ticket bound to exact target, principal and permission | `ws_ticket` |
| `WS /api/v1/ws/tasks/{task_id}` | Valid consumed task ticket | Exact task scope; no anonymous connection | ticket consumption |
| `GET /api/v1/runtime/threads/by-task/{task_id}` | `runtime:read` | Minimized thread/checkpoint metadata | general read |
| `GET /api/v1/runtime/threads/{thread_id}` | `runtime:read` | Minimized thread/checkpoint metadata | general read |
| `GET /api/v1/runtime/threads/{thread_id}/history` | `runtime:read` | Bounded history, no raw checkpoint payload | general read |
| `GET /api/v1/runtime/threads/{thread_id}/intervention` | `runtime:read` | Safe eligibility/context; permission result can be `NO_PERMISSION` | general read |
| `POST /api/v1/runtime/threads/{thread_id}/overrides` | `runtime:override` | Existing business validation unchanged; actor from principal | `runtime_override` |
| `GET /api/v1/runtime/threads/{thread_id}/overrides` | `runtime:read` | Operational history; actor/reason/evidence redacted unless `audit:read` | general read |
| `GET /api/v1/runtime/overrides/{override_id}` | `runtime:read` | Same field projection rule | general read |
| `POST /api/v1/memory/mutations` | `memory:mutate` | Actor from principal; `human_confirmed` never authorizes | `memory_mutation` |
| `GET /api/v1/memory/mutations/{mutation_id}` | `memory:read` | Safe mutation state; actor/evidence requires `audit:read` | general read |
| `GET /api/v1/memory/facts/{fact_key}` | `memory:read` | Safe canonical/projection DTO; evidence minimized | general read |
| `GET /api/v1/observability/summary` | `monitor:read` | Fixed query catalog only | `observability_read` |
| `GET /api/v1/observability/agents` | `monitor:read` | Fixed typed DTO | `observability_read` |
| `GET /api/v1/observability/workers` | `monitor:read` | Fixed typed DTO | `observability_read` |
| `GET /api/v1/observability/memory` | `monitor:read` | Fixed typed DTO | `observability_read` |
| `GET /api/v1/observability/runtime` | `monitor:read` | Fixed typed DTO | `observability_read` |
| `GET /api/v1/observability/dependencies` | `monitor:read` | Fixed typed DTO; no credentials/URLs beyond approved safe link | `observability_read` |
| `GET /api/v1/security/audit` | `audit:read` | Bounded `limit` 1–500; typed safe event records only | general read |

The implemented security-audit read projection is limited to `GET /api/v1/security/audit` and requires `audit:read`. No audit mutation endpoint is exposed; business audit remains on its existing dispatch result boundary.

Orders, Anomalies, Agents, and dashboard summary pages currently do not all have matching backend endpoints. This design does not invent business APIs. When an existing product read API is exposed later, it must map respectively to `orders:read`, `anomalies:read`, `agents:read`, or the explicit permissions of its constituent data.

## 4. Field-level response rules

| Data | Base permission | Additional permission for sensitive detail |
|---|---|---|
| Dispatch status/decision | `dispatch:read` | `audit:read` for full review evidence beyond current safe summary |
| Runtime current state/version/next node | `runtime:read` | Raw checkpoint payload is prohibited even with admin |
| Override status/old→new/version | `runtime:read` | `audit:read` for actor, role, full reason, evidence, detailed checkpoint identifiers |
| Shared Memory value/projection status | `memory:read` | `audit:read` for actor, source, evidence, and full mutation audit |
| Observability/Security aggregates | `monitor:read` | Individual security events require `audit:read` |
| Security/business audit | `audit:read` | Secret fields are prohibited for every role, including admin |

This is implemented through separate typed projections or a server-owned projection function. It is never achieved by serializing a full model and deleting a few keys after the fact.

## 5. Authorization flow

```text
Bearer credential
  → AuthenticationProvider
  → AuthenticatedPrincipal
  → require_permission(required)
  → resource authorizer(principal, canonical resource)
  → exact-idempotency replay check where applicable
  → rate-limit admission
  → existing business service/policy
  → security/business audit
```

Authentication failures are 401, authorization failures are 403, throttling is 429, security-control unavailability is a bounded 503, and business conflicts retain their current 409/422 semantics.

## 6. Principal and actor rules

- `subject_id` is the durable audit actor key; `display_name` is presentation only.
- Role and permission values come from the server-owned mapper. A request cannot add them.
- Runtime Override and Shared Memory commands receive server-built actor data separately from the untrusted request DTO.
- If legacy DTO compatibility temporarily accepts `operator_id`, the parser uses `extra="forbid"` for all other fields and the server rejects a mismatch; the target contract removes the field entirely.
- `human_confirmed`, `expected_version`, `reason`, `idempotency_key`, and scope IDs remain untrusted business inputs and never imply permission.
- Security metrics never use subject as a label; subject may appear only in access-controlled audit records and safe diagnostic logs.

## 7. Resource policy

CountyFlow V2-G2 has one organization and no region/owner/tenant claim. Therefore:

- A permitted principal may access every current resource of that type in this deployment.
- Path IDs are checked against canonical MySQL/registry records after permission admission.
- Task-ticket scope binds the exact task; a ticket for one task cannot subscribe to another.
- Runtime and Memory never accept client-supplied ownership or permission metadata.
- A future tenant or region design is a new security phase; it cannot be emulated with string prefixes.

## 8. Contract tests

`ROLE_PERMISSION_MATRIX` is one immutable source used by the server mapper and contract tests. Required assertions include:

- Supervisor has `runtime:override` and Memory mutation.
- Dispatcher lacks `runtime:override`, `memory:mutate`, `audit:read`, and `monitor:read`.
- Auditor cannot dispatch, mutate, review, or override.
- Operator cannot dispatch, mutate, review, or override.
- Admin contains every explicit permission.
- No non-admin role contains `system:admin`.
- Every protected route appears exactly once in an endpoint-permission registry/contract test.
- Direct HTTP calls receive 403 even when the frontend control is hidden.
- Full actor/reason/evidence projections require `audit:read`.
