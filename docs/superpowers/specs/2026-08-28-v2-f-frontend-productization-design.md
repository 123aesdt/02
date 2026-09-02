# CountyFlow V2-F Frontend Productization Design

## Status and scope

This specification productizes the already-accepted V2-A through V2-E capabilities in the existing CountyFlow operations console. It preserves the current navigation, dark enterprise theme, routes, backend algorithms, storage responsibilities, and asynchronous execution path.

V2-F may add only safe read DTO fields and safe WebSocket event fields that already exist in backend domain state. It must not add a new business algorithm, mutation capability, graph query language, runtime control operation, persistence mechanism, or V2 portal.

## Product outcome

An operator can understand and demonstrate the V2 system without reading source code:

- the eight-agent topology is visible in the correct order;
- Vector Memory, Graph Memory, and Shared Memory Control Plane have separate, clear surfaces;
- graph entities, relations, bounded paths, evidence, confidence, projection status, and control version are inspectable;
- runtime thread, checkpoints, backend eligibility, override operation, downstream capacity/routing impact, history, and audit evidence form one explainable flow;
- infrastructure and verified acceptance evidence are visible without presenting historical evidence as live telemetry.

## Locked product structure

The existing primary navigation remains:

1. Dashboard
2. Anomalies
3. Orders
4. Agents
5. Memory
6. Monitoring

Runtime intervention remains inside Dispatch Detail. Memory uses three tabs: Vector, Graph, and Shared Control.

## Data provenance contract

Every V2 surface belongs to one of three explicit provenance classes:

| Provenance | Meaning | UI treatment |
| --- | --- | --- |
| Live API | Current response from an existing backend endpoint | `LIVE API` source label |
| Live Event | Current task data reconstructed from the existing task WebSocket event contract | `LIVE EVENT` source label |
| Verified Baseline | Immutable V2-E acceptance evidence | `VERIFIED ACCEPTANCE` label and timestamp/context copy |

Mock mode is a fourth development-only mode and must be labelled `DEMO DATA`. API mode never falls back to mock data when an endpoint, event stream, or service is unavailable; it renders an explicit loading, empty, unavailable, or error state.

## Visual system

The accepted visual target is the existing CountyFlow console:

- dark blue-black operating surface;
- restrained teal success, amber attention, red risk, and violet memory accents;
- compact tables, rails, timelines, and inspectors;
- existing typography, border radius, spacing, Lucide icon family, and navigation shell;
- textual status labels in addition to color;
- no neon glow, game UI, large gradient decoration, new hero area, or card-heavy portal.

No new image asset is required. The graph is a functional code-native SVG data visualization, not decorative artwork.

## Dashboard V2

Dashboard adds a compact capability summary for 8 Agents, Vector Memory, Graph Memory, Shared Memory, Runtime Threads, Runtime Overrides, and the four persistence services. It links to the existing detail routes.

In mock mode, operational content is clearly marked Demo Data. In API mode, the current backend connection/runtime profile comes from `/health`; V2-E results are shown only as Verified Acceptance. The current hard-coded QPS/P95/worker values must not masquerade as live metrics.

## Eight-agent topology

The canonical order is:

1. Intake
2. Entity Memory
3. Graph Memory
4. Environment
5. Capacity
6. Routing
7. Dispatch
8. Audit

The shared `AgentPipeline` and Agents page use this order. In API mode, task execution states and details derive from existing WebSocket events. The Agents page accepts a task ID so a real task can be inspected without inventing an aggregate metrics endpoint. Graph Memory detail shows role, input boundary, entity/relation/path counts, elapsed time, status, and failure degradation.

## Memory workspace

### Vector tab

The Vector tab preserves the current Qdrant memory record experience. Mock records are labelled Demo Data. The V2-E Top-1 49/50, Top-3 50/50, provider/model, and dimension are shown as Verified Acceptance, not live recall telemetry.

### Graph tab

In API mode the operator enters a task ID; the page consumes the existing task WebSocket history and reconstructs graph evidence from `GRAPH_MEMORY_*` events. In mock mode it renders the approved V2 graph example as Demo Data.

The graph uses a small responsive SVG with typed nodes and labelled edges. Keyboard-focusable node controls support select and Enter/Space activation. Selecting or hovering a node updates a property inspector. A separate path inspector lists node/relation steps, hop count, confidence, source/evidence, control version, and projection status when supplied by the backend.

The graph traversal is not performed in the browser. It only renders the bounded paths already emitted by the backend.

### Shared Control tab

Shared Control retains fact-key lookup against the existing read endpoint. The canonical fact summary shows key, category, version, confidence, status, expiry, Qdrant projection, Neo4j projection, and last mutation. Mutation history shows decision, before/after version, incoming confidence, operator/source, time, and per-projection result.

Projection labels distinguish STAGED, FINALIZING, ACTIVE, RETIRED, FAILED, and NOT_REQUIRED. STAGED and FINALIZING are visually and textually identified as not yet active.

## Dispatch runtime workbench

Runtime Thread adds worker consumer and updated time. Checkpoint ID and state version use separate labels and never share a single version token.

The checkpoint timeline combines existing runtime-thread history and override history into one chronologically ordered view:

- agent checkpoint entries show node, checkpoint ID, and checkpoint state version;
- runtime override entries show requested/applied status, old/new value, before/after state version, source/result checkpoint, actor, reason, and time.

Eligibility remains entirely backend-driven. The dialog supports only the existing Vehicle.status transitions, includes the required context/risk warning, traps focus, closes on Escape, restores focus, and exposes disabled reasons as text.

Capacity, Routing, and Audit panels display only backend event/result data. Routing explains capacity constraints, candidates, excluded resources, and final decision without manufacturing an override causal statement.

## Monitoring

Monitoring contains:

- a Live Backend section based on `/health`, including runtime/provider configuration when returned;
- the nine-service product topology, with Backend, Worker-1, Worker-2, Redis, MySQL, Qdrant, and Neo4j explicitly visible; service states not returned by `/health` are `NOT EXPOSED`, never guessed healthy;
- Verified Acceptance sections for Vector/Graph memory, shared-memory consistency, runtime override/checkpoint/recovery, and Locust performance.

Verified baselines are copied from the existing V2-E evidence and visibly marked as non-live.

## Minimal backend read-contract additions

Only fields already present in backend state/models may be exposed:

1. Runtime thread read DTO: `worker_consumer` and `updated_at`.
2. Shared fact read DTO: category, fact kind, subject, predicate/object, projection identifiers, last mutation, updated time, mutation source/operator/confidence/completion metadata.
3. Routing event: existing `candidate_routes`, `decision_reason`, and `requires_manual_review` values.
4. Audit event: existing `audit_result` safe fields.

These changes do not alter execution, persistence, reconciliation, routing, or audit semantics.

## Accessibility and responsive acceptance

- Dialog has an accessible name, initial focus, focus containment, Escape close, and focus restoration.
- Disabled intervention actions expose backend reason text.
- Status is always conveyed by text and color.
- Tabs use tab roles and keyboard-accessible buttons.
- Graph nodes are keyboard selectable and expose accessible labels.
- Tables and timelines remain readable at 1440 and 1920 desktop widths without horizontal clipping of primary content.

## Testing and evidence

Each behavior is implemented with RED, observed failure, minimal GREEN, and refactor. Required evidence includes frontend unit tests, targeted backend contract tests, Playwright browser E2E, 12 named screenshots under `docs/verification/v2-f/screenshots`, frontend lint/test/build, backend regression, `check.ps1`, Docker nine-service status/E2E, secret scan, and Git whitespace/status checks.

The V2-E embedding, 50-override, 15-round black-box, Locust, worker-kill, graph, and shared-memory heavy suites are not recalculated because V2-F does not change their semantics. Their existing evidence is reused and labelled.

## Explicit non-goals

- no V2-G or new backend capability;
- no new top-level route or V2 portal;
- no graph mutation/query builder;
- no frontend-derived intervention eligibility;
- no frontend-local fake override or capacity state;
- no routing algorithm or checkpoint semantics changes;
- no new monitoring collector;
- no large graph dependency;
- no external embedding call or V2-E heavy rerun;
- no commit, merge, PR, or Git author modification.
