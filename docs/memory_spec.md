# CountyFlow Memory Specification

## Memory layers

CountyFlow V2-A uses two complementary long-term memory systems while MySQL remains the business source of truth.

| Store | Responsibility | Query style | May control running state? |
| --- | --- | --- | --- |
| MySQL | Orders, tasks, dispatches, audit facts | transactional lookup | business truth only |
| Qdrant | Semantically similar historical cases | vector Top-K | no; routing may adopt V1 evidence |
| Neo4j | Explicit entity relations and bounded paths | allowlisted 1-3 hop traversal | no |

Graph Memory does not replace `memory_results`, `memory_adopted`, or `adopted_memory_id`. It adds relationship evidence. LangGraph checkpoint state remains distinct from Neo4j long-lived facts.

## Entity schema

All nodes carry `GraphEntity` plus exactly one application-controlled type label. Allowed types are `Driver`, `Vehicle`, `Route`, `Weather`, `RoadCondition`, `Station`, `Anomaly`, `Resolution`, `DispatchOrder`, `PolicyRule`, and `UserPreference`.

The domain value is frozen and serializable:

- `entity_type`: allowlisted type;
- `entity_id`: stable business identifier;
- `entity_key`: `<entity_type>:<entity_id>`;
- `display_name`: safe human-readable name;
- `properties`: JSON-compatible metadata.

Neo4j stores `properties` as a JSON string so driver objects and nested maps never enter graph state.

## Relation schema

Allowed types are `DRIVES`, `SERVES`, `HAS_RISK_ON`, `AFFECTED_BY`, `HIGH_RISK_WHEN`, `ALTERNATIVE_TO`, `RESOLVED_BY`, `CONFLICTS_WITH`, `DEPENDS_ON`, and `STATUS`.

Every relation contains source and target entity keys, confidence in `[0,1]`, source type, optional evidence, positive version, timestamp, and a deterministic identity derived from source/type/target. V2-A does not implement relation conflict resolution or forgetting.

## Constraints and indexes

Startup bootstrap executes idempotent `IF NOT EXISTS` statements:

- unique constraint: `GraphEntity.entity_key`;
- index: `GraphEntity.entity_id`;
- index: `GraphEntity.entity_type`.

Bootstrap never drops constraints, deletes nodes, or recreates the graph.

## Repository and service boundary

`GraphMemoryRepository` provides entity/relation upsert, entity lookup, related-fact recall, and bounded path recall. `Neo4jGraphMemoryRepository` alone owns Cypher, transaction execution, driver mapping, timeout configuration, and safe error translation. Agents call `GraphMemoryService`; they never import the Neo4j driver.

`GraphMemoryService` invokes `GraphTripleExtractor`, persists explicit candidates, chooses query anchors, performs capped recall, and returns `GraphMemoryRecall`. Default traversal is two hops, accepted depth is one to three, and every query has a result limit and timeout.

## Triple extraction

V2-A uses a deterministic domain extractor. For “李师傅驾驶冷链车A，在雨天经过新平路时报告道路湿滑。” it identifies the driver, vehicle, route, rain, and rain-slippery anomaly plus only relations supported by the input. It never extracts `national-102` or `ALTERNATIVE_TO` from that sentence; those must be recalled from Neo4j.

`GraphTripleExtractor` is the future extension boundary. LLM extraction is explicitly outside V2-A.

## Seed

The idempotent development seed contains seven entities: `driver-li`, `vehicle-cold-a`, `xinping-road`, `national-102`, `rain`, `rain-slippery`, and `reroute-national-102`. Vehicle `vehicle-cold-a` has the long-lived fact property `status=normal`.

It contains five meaningful relations:

- `driver-li -[DRIVES]-> vehicle-cold-a`;
- `driver-li -[HAS_RISK_ON]-> xinping-road`;
- `xinping-road -[HIGH_RISK_WHEN]-> rain`;
- `national-102 -[ALTERNATIVE_TO]-> xinping-road`;
- `rain-slippery -[RESOLVED_BY]-> reroute-national-102`.

Running the seed repeatedly uses `MERGE` and does not increase seed entity or relation counts.

## Agent state and degradation

The Graph Memory Agent is placed between Entity Memory and Environment. Its patch contains `graph_memory_facts`, `graph_memory_paths`, `graph_memory_used`, `graph_memory_error`, and `graph_memory_elapsed_ms`. All values are JSON serializable.

Known `GraphMemoryError` failures yield empty evidence, `graph_memory_used=false`, and a safe error message. Environment, Capacity, Routing, Dispatch, and Audit continue. `CancelledError` is not swallowed. Audit persists only compact entity/relation/path summaries, not a graph dump.

## Cypher security

All entity IDs, names, evidence, keys, limits, and other user-derived values use Cypher parameters. Labels and relationship types cannot be parameterized, so they are produced only by `EntityType` and `RelationType` enums. Traversal depth is validated as an integer from one to three before it is inserted into the query text. Malicious label/type strings are rejected before repository execution.

## Docker lifecycle and real integration

Docker Compose runs `neo4j:5.26-community` with an authenticated Bolt endpoint, healthcheck, and persistent `countyflow_neo4j` volume. The migration service waits for health, bootstraps schema, and seeds the graph. Workers receive the real driver through runtime dependency injection and close it during cancellation-safe shutdown.

`scripts/test-graph-memory.ps1` calls the real-server integration runner. It verifies connectivity, repeated schema/seed execution, expected seed counts, all three core relationship facts, domain mapping, and 20 warm-query min/avg/p95/max timing without printing credentials.

## V2-B shared memory control plane

V2-B adds a write coordinator without combining the existing Vector and Graph read services. The write path is `SharedMemoryMutationCommand -> SharedMemoryMutationService -> Redis fact lock -> MySQL control plane -> Qdrant/Neo4j projections -> audit event`.

MySQL owns the canonical `SharedMemoryFact`, its version/status/confidence/expiry, append-only evidence provenance, mutation ledger, and retry attempts. Redis provides only `SET NX PX` mutual exclusion under `countyflow:lock:memory:<fact_key>`; MySQL unique constraints and SQLAlchemy `version_id_col` remain the final consistency guards. Qdrant and Neo4j store projections tagged with the MySQL control version and never evolve independent versions.

The first implemented category is `DispatchMemory`. `ChatMemory`, `LLMWiki`, and `CodeGraph` may be represented by enums but are rejected by the V2-B service.

### Fact identity and mutation identity

Canonical JSON uses sorted keys, compact separators, normalized enums, and UTF-8. SHA-256 produces:

- `fact_key`, a stable logical slot key;
- `content_fingerprint`, semantic fact equality excluding evidence/confidence;
- `payload_fingerprint`, exact idempotency replay comparison;
- `evidence_fingerprint`, provenance deduplication.

Single-valued attributes such as `Vehicle STATUS` exclude the changing value from `fact_key`, so `Normal` and `Broken` conflict in the same slot. Set-valued relationships include the object identity.

### Mutation decisions and lifecycle

The deterministic decisions are CREATE, MERGE, REPLACE, REJECT, CONFLICT_REVIEW, and NOOP. Low-confidence unconfirmed input is held for review without an active data-plane write. Expected-version mismatch raises a version conflict before any projection call. Accepted new evidence is MERGE and increments the fact version; a complete duplicate is NOOP and does not.

Mutation states are PENDING, APPLYING, FINALIZING, APPLIED, PARTIAL, REJECTED, CONFLICT, and FAILED. Vector/graph states are NOT_REQUIRED, PENDING, STAGED, ACTIVE, RETIRED, and FAILED. A staging failure leaves the old canonical fact and old ACTIVE projections unchanged. `MemoryMutationReconciler.resume_mutation(mutation_id)` probes deterministic projection identities, skips already STAGED/ACTIVE work, retries missing work, advances MySQL once, and finishes activation/retirement.

### Projection visibility and crash safety

Every new Qdrant point and Neo4j relationship follows `STAGED -> ACTIVE`; the previous visible version follows `ACTIVE -> RETIRED`. Payloads/properties contain `fact_key`, `control_version`, `projection_status`, and `mutation_id`. Normal Entity Memory and Graph Memory recall admits only ACTIVE V2-B projections; legacy V1/V2-A records without projection metadata remain compatibility-readable. STAGED and RETIRED records never enter normal Top-K or bounded graph recall.

The write sequence is stage every required projection, commit the prospective MySQL canonical version with mutation status FINALIZING, activate the new versions, retire prior ACTIVE versions, prove the store states, then mark APPLIED. APPLIED therefore means MySQL is at the new version, every required new projection is ACTIVE, and no previous projection remains ACTIVE. If a process crashes after MySQL finalization but before activation, the mutation API reports projection incomplete/reconciling and `resume_mutation()` completes the idempotent activation without adding a point or edge.

### Evidence, audit, and security

Evidence uses a separate append-only `memory_evidence` table rather than an unbounded JSON array in the current fact. Mutation request/decision identity is immutable; each apply/resume attempt is append-only. Evidence text is sanitized and capped at 2,000 characters; reasons, summaries, and references are bounded. Credentials, Authorization headers, driver/session objects, raw embeddings, and provider dumps are forbidden from persistence and events.

### Read and runtime boundaries

Existing Qdrant semantic scoring and Neo4j bounded traversal remain independent. Projection adapters add only ACTIVE/expiry compatibility filters, treating V1/V2-A records without projection metadata as active. Control-plane reads compare the canonical version with per-store lifecycle state and explicitly expose incomplete/reconciling status; they never report APPLIED prematurely. Shared mutation objects never enter `DispatchGraphState`, and the eight-agent graph does not change. Runtime override and checkpoint mutation remain deferred.

## Deferred boundaries

V2-A did not implement mutation control. V2-B designs DispatchMemory mutation, versioning, conflict, logical expiry, partial recovery, and audit. Runtime State Override, LangGraph checkpoint mutation, authenticated human intervention, automatic reconciliation scheduling, physical TTL cleanup, ChatMemory, LLMWiki, CodeGraph behavior, and LLM graph extraction remain deferred to explicitly approved later phases.
