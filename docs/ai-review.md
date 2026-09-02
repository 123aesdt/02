# CountyFlow V2.0 AI Code Review

Review date: 2026-08-27. Scope: V2-A through V2-E integration boundaries.

Status: **PASS with one external verification blocker**

## Reviewed controls

- Cancellation: `asyncio.CancelledError` is re-raised; projection operation timeouts are normalized to auditable PARTIAL results.
- SQLAlchemy sessions: repositories use bounded context-managed sessions and rollback conflict paths.
- Redis lifecycle: API, worker, runtime checkpoint, and lock clients are closed on shutdown; owner-token releases occur in `finally` paths.
- Checkpoint lifecycle: official saver setup/close is paired; canonical promotion and orphan isolation are explicit.
- Neo4j lifecycle: drivers are injected behind Repository/Service boundaries and closed by application/script owners; values are parameterized and labels/types are allowlisted.
- Qdrant lifecycle: clients are closed by application/script owners. V2-E corrected synchronous projection operations so they no longer block the asyncio timeout boundary.
- HTTP clients: provider timeouts are explicit; owned clients use context management/close paths; secret-bearing headers are not logged.
- Worker shutdown/recovery: cancellation-safe stop, bounded retries, XACK after durable terminal state, and XAUTOCLAIM recovery are covered by real Redis tests.
- Event dedupe: idempotency keys and durable uniqueness prevent duplicate task/dispatch/audit results.
- Projection consistency: STAGED is hidden, ACTIVE is visible, RETIRED is hidden, and partial resume is idempotent.
- Override atomicity: authorization, Redis boundary lock, MySQL state-version CAS, checkpoint update, and canonical promotion preserve single-winner behavior.
- Secret and audit payloads: credentials stay in ignored environment files; override reasons and audit evidence contain business-safe text only.

## Finding resolved during V2-E

Stopping a projection dependency exposed that an async service called the synchronous Qdrant client directly and a later Neo4j operation could consume the total timeout. The projection calls now run off the event loop and each projection has a shorter bounded timeout. Regression tests prove a hung projection becomes `PARTIAL` with `PROJECTION_TIMEOUT`; real browser fault injection proves PARTIAL-to-APPLIED reconciliation.

## Residual observations

- Qdrant client 1.19 reports a compatibility warning against server 1.13.2; exercised APIs passed, but version alignment is recommended in a future dependency-maintenance phase.
- The external Qwen embedding regression is not code-review evidence and remains unverified because host policy denied the credentialed outbound request.
