# CountyFlow V2-G2 Security Runbook

**Status:** IMPLEMENTED AND VERIFIED — operational controls validated on 2026-08-29

**Audience:** CountyFlow operator, supervisor, auditor, and incident responder

## 1. Safety rules

- Never paste or print an access token, refresh material, cookie, Authorization header, JWT signing secret, API key, database URL, or password.
- Use request ID, UTC time window, bounded reason code, route class, and subject ID from access-controlled audit—not raw headers or bodies—to correlate an event.
- Do not turn on development auth, anonymous Grafana, public Prometheus, or fail-open writes to restore service.
- Do not edit business audit or security audit records. Preserve evidence and record every mitigation.
- Production secrets are rotated through environment/orchestration secret injection and controlled restart. They are never passed as command-line arguments.

## 2. Session/token invalid or expired

Expected signals:

- Browser shows `SESSION EXPIRED` and stops sensitive requests/WebSockets.
- HTTP returns 401 with a stable code such as `TOKEN_EXPIRED` or `TOKEN_INVALID`.
- `countyflow_authentication_failures_total` increases with a bounded reason code.

Checks:

1. Confirm environment/profile and UTC clocks without inspecting token contents.
2. Confirm configured issuer, audience, JWKS reachability, and key rotation status by configuration name/health only.
3. Correlate `request_id`, route class, timestamp, and safe reason code in security audit.
4. Distinguish one expired session from a platform-wide unknown-`kid`, wrong-audience, or issuer outage.

Response:

- Single expired token: reauthenticate through OIDC in production; docker-dev renews its automatic in-memory development session without a manual token form.
- Unknown key after a planned rotation: verify overlapping JWKS keys and bounded refresh; do not relax the algorithm/issuer/audience checks.
- Suspected stolen token: revoke its JTI through the approved authenticated administrative boundary, then reauthenticate the user. Redis revocation TTL must equal only the remaining token lifetime.
- Provider outage: protected writes stay fail closed. Announce the bounded outage; never activate development auth in production.

Evidence to preserve: alert name, UTC window, request IDs, safe reason-code counts, provider health state, mitigation and recovery time. Do not preserve raw tokens.

## 3. Authorization-denied spike

Dashboard/alert: `AuthorizationDeniedSpike` or `RuntimeOverrideDeniedSpike`.

1. Check route class and required permission; never group by token or expose the request body.
2. Compare against deployment/role-mapping changes and normal direct-bypass/security tests.
3. Use access-controlled audit to identify whether denials are one principal, a client version issue, or broad privilege probing.
4. Confirm the denied request did not invoke the business service and did not create an override/mutation.

Mitigation:

- Mapping/config regression: restore the last approved role mapping through normal deployment controls; do not grant wildcard permission.
- Suspected abuse: revoke active JTI(s), preserve evidence, and limit the account at the identity provider.
- Expected operator error: correct role assignment at the external identity boundary; do not accept roles from request bodies.

Closure requires the alert to clear, direct API denial still to pass, and no unauthorized business record to exist.

## 4. Rate-limit spike

Dashboard/alert: `RateLimitSpike`; API returns `429 RATE_LIMIT_EXCEEDED` with `Retry-After`.

1. Identify operation class (`dispatch_submit`, `runtime_override`, `memory_mutation`, `observability_read`, `ws_ticket`, or invalid authentication).
2. Verify Redis health and latency; a limiter outage is not the same as valid throttling.
3. Correlate subject only in access-controlled audit. Never add subject/IP to Prometheus labels.
4. Check whether repeated calls are exact idempotent retries, client retry storms, WebSocket reconnect churn, or intentional abuse.

Mitigation:

- Client retry storm: stop/redeploy the client and honor `Retry-After`; do not globally disable the limiter.
- Legitimate sustained load: validate with business owner and performance evidence, then change the named operation configuration through review.
- Abuse: revoke identity/session and apply provider/network controls as appropriate.
- Redis unavailable: high-risk writes remain closed; bounded reads may use only the documented local emergency cap.

Redis restart resetting buckets is acceptable and must be recorded; it does not restore or alter business truth.

## 5. WebSocket ticket rejection spike

Dashboard/alert: `WsTicketRejectionSpike`.

Checks:

- Missing/expired/replayed ticket versus wrong task scope.
- Ticket issuance succeeded and Redis is healthy.
- Client obtains a new ticket on reconnect instead of reusing the old value.
- No access token is present in the URL or access log.
- The task target and `dispatch:read` permission were checked at issuance.

Response:

- Client bug: stop reconnect storm, fix fresh-ticket acquisition, and retain API-mode no-Mock behavior.
- Replay/wrong scope: revoke the session if suspicious and preserve safe audit events.
- Redis outage: ticket admission stays closed; use status polling only if the principal is authenticated and authorized.

## 6. Key and credential rotation

General sequence:

1. Schedule and identify the exact credential by name, never by value.
2. Confirm backup/recovery and service-owner availability.
3. Introduce a new credential/key through ignored environment or orchestration secret injection.
4. Where supported, overlap old and new server credentials/keys.
5. Restart or reload only the affected services through the approved deployment path.
6. Verify health, one safe authenticated request, audit/metrics, and dependency connectivity.
7. Revoke/remove old material.
8. Run the secret-artifact scan and record `0 findings` without printing values.

Specific boundaries:

- OIDC/JWT public keys: publish overlapping JWKS `kid`, allow bounded cache refresh, then retire old key after maximum token TTL.
- Docker-dev JWT secret: replace ignored secret and restart backend; all dev tokens expire immediately. Never do this provider flow in production.
- Embedding API key: rotate at provider, update ignored/deployment secret, restart Backend/Workers if configured there, and verify without logging headers.
- MySQL/Neo4j/Redis/Grafana: use distinct credentials. Rotate server then clients when overlap is supported; otherwise use a controlled maintenance restart. Neo4j must never reuse `MYSQL_PASSWORD`.

## 7. Security incident inspection

Use this bounded sequence:

1. Establish UTC start/end time and affected route/operation class.
2. Open the Grafana Security section and V2-G1 dependency/HTTP panels.
3. Query access-controlled security audit by event type, safe reason code, request ID, and subject when authorized.
4. Correlate existing business audit for dispatch/override/mutation outcomes.
5. Verify current token/JTI revocation and role mapping without decoding or copying the raw token into tooling.
6. Check worker/queue/checkpoint continuity separately; security denial must not be confused with business failure.
7. Preserve safe artifacts, mitigations, and recovery timestamps.

Escalate immediately when any of these is true:

- An unauthorized override or memory mutation was applied.
- A production process used development/trusted auth.
- A token/key/cookie/password appeared in logs, JSON, Markdown, screenshots, Git diff, or artifacts.
- Prometheus is publicly reachable or Grafana permits anonymous/admin-default access.
- Audit integrity is uncertain.

Containment order is revoke identity/key, close exposed access, preserve evidence, validate business state, rotate affected credentials, and run regression/secret scans. Do not delete evidence during containment.

## 8. Audit retention and health

- Default security-audit retention is 180 days; approved configuration range is 30–365 days.
- Cleanup operates on records older than the configured UTC cutoff in bounded batches and requires an explicit maintenance identity.
- No application role can update/delete individual audit rows.
- Before cleanup, record cutoff, count, request ID, and operator in the maintenance audit; never export secrets or full request bodies.
- If audit writes fail, denied requests remain denied and high-risk admitted writes fail closed before business mutation.

## 9. Recovery verification checklist

- Authentication succeeds only with correct issuer/audience/time/algorithm.
- Revoked or expired tokens remain rejected.
- Dispatcher direct override POST is 403.
- Supervisor override still passes existing V2-D1 business rules.
- Auditor and Operator remain read-only for their approved scopes.
- Task WebSocket requires a fresh, scoped, one-time ticket.
- Redis limiter is per principal and emits correct `Retry-After`.
- Security audit contains safe actor/event/reason/request fields and no secret/body.
- Security metrics are visible with only low-cardinality labels.
- Grafana requires authentication; Prometheus and `/metrics` remain internal.
- API mode does not fall back to Mock.
- Secret-artifact scan returns `0 findings`.
- Normal authenticated performance remains QPS `>=200`, P95 `<300 ms`, error rate `<0.1%` when performance verification is required.
