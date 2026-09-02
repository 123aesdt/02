# CountyFlow V2-A Graph Memory Design

## Goal and scope

V2-A adds Neo4j Community Edition as a relationship-memory store and inserts a Graph Memory Agent into the existing asynchronous dispatch graph. It preserves the V1 FastAPI, Redis Streams, worker, MySQL, Qdrant, WebSocket, dispatch, audit, and routing behavior. Runtime override, checkpoint mutation, memory merge/conflict policy, approval intervention, TTL/forgetting, and LLM triple extraction remain deferred.

## Memory responsibilities

- MySQL remains the source of truth for orders, tasks, dispatches, and audit records.
- Qdrant Vector Memory continues semantic recall of similar historical cases and keeps all existing state fields and routing adoption behavior.
- Neo4j Graph Memory stores allowlisted long-lived entities, explicit relations, and bounded relationship paths. It is evidence, not the truth for a running LangGraph checkpoint.
- LangGraph state contains only JSON-serializable business values. Drivers, sessions, repositories, and services remain in `GraphDependencies` or runtime factories.

## Graph entity schema

`GraphEntity` is a frozen domain value with `entity_type`, `entity_id`, `display_name`, and JSON-compatible `properties`. Supported entity types are `Driver`, `Vehicle`, `Route`, `Weather`, `RoadCondition`, `Station`, `Anomaly`, `Resolution`, and `DispatchOrder`; `PolicyRule` and `UserPreference` may be defined without V2-A business logic.

Every node has the base label `GraphEntity`, one allowlisted type label, and a globally unique `entity_key` derived as `<entity_type>:<entity_id>`. The stored fields include `entity_type`, `entity_id`, `display_name`, `properties`, `created_at`, and `updated_at`. Entity types are validated before Cypher construction.

## Graph relation schema

`GraphRelation` is a frozen domain value with source and target entity references, an allowlisted `relation_type`, `confidence`, `source_type`, optional `evidence`, `version`, and timestamp. V2-A relations are `DRIVES`, `SERVES`, `HAS_RISK_ON`, `AFFECTED_BY`, `HIGH_RISK_WHEN`, `ALTERNATIVE_TO`, `RESOLVED_BY`, `CONFLICTS_WITH`, `DEPENDS_ON`, and `STATUS`.

Relationship identity is deterministic from source key, relation type, and target key. `MERGE` makes seed and normal upserts idempotent. User values are parameters; only enum-to-literal mappings supply labels and relationship types.

`GraphPath` contains ordered `GraphEntity` and `GraphRelation` domain values. `GraphMemoryRecall` contains query entities, deduplicated facts, bounded paths, and elapsed milliseconds. No Neo4j object crosses the repository boundary.

## Constraints and indexes

Schema bootstrap uses `IF NOT EXISTS` and never deletes data:

- unique constraint on `GraphEntity.entity_key`;
- index on `GraphEntity.entity_id`;
- index on `GraphEntity.entity_type`.

Schema bootstrap is safe to repeat. Type-specific labels are used only for controlled matching and human inspection; identity is enforced through the base label.

## Repository boundary

`GraphMemoryRepository` is an async protocol providing entity upsert/read, relation upsert, related-fact recall, and bounded path recall. `Neo4jGraphMemoryRepository` owns Cypher, parameter serialization, transaction/session boundaries, timeout configuration, and mapping driver exceptions to `GraphMemoryError`. `FakeGraphMemoryRepository` is deterministic test infrastructure and implements the same observable behavior.

Queries require `1 <= max_hops <= 3`, default to two hops, and cap result count. No unbounded `[*]` traversal is permitted.

## Extraction and service boundary

`GraphTripleExtractor` is a protocol returning candidate entities and relations. V2-A uses a deterministic domain extractor that maps the normalized driver, vehicle, route, weather, and anomaly context into stable graph values. It never infers an alternative route from the current sentence; that fact must come from graph recall.

`GraphMemoryService` accepts a serializable business context, extracts query entities and explicit input relations, upserts those candidates, then recalls allowlisted facts and paths around driver, route, and weather anchors. It returns `GraphMemoryRecall` and hides repository details.

## Agent and graph state

`graph_memory_node(state, service)` reads `DispatchGraphState` and emits a patch with:

- `graph_memory_facts`: compact serializable relation facts;
- `graph_memory_paths`: serializable ordered path summaries;
- `graph_memory_used`: whether graph evidence was returned;
- `graph_memory_error`: a safe message or `None`;
- `graph_memory_elapsed_ms`: query timing.

Known `GraphMemoryError` failures degrade safely to empty evidence and `graph_memory_used=false`. Cancellation is not caught. `GraphDependencies.graph_memory_service` is optional in local/test graphs and required for production runtime configuration.

The topology becomes:

`START -> intake -> entity_memory -> graph_memory -> environment -> capacity -> routing -> dispatch -> audit -> END`

Routing may include graph facts in explanations but its V1 decision algorithm is unchanged. Audit receives a compact graph evidence summary rather than a full graph dump.

## Events and frontend

The existing event adapter publishes `GRAPH_MEMORY_STARTED`, `GRAPH_MEMORY_COMPLETED`, and, on safe degradation, `GRAPH_MEMORY_DEGRADED`. API and mock frontends both show Graph Memory between Entity Memory and Environment. Dispatch detail renders event-sourced entities, relations, and paths, using an em dash when absent.

## Docker and lifecycle

Docker Compose adds the official Neo4j Community service with persistent storage, authentication from environment variables, an internal dependency chain, and a healthcheck. Migration/bootstrap waits for Neo4j health, creates constraints/indexes, and applies the idempotent development seed. Backend and workers receive `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, and `NEO4J_DATABASE` through environment configuration.

Runtime profiles are:

- `test`: fake/controlled repository;
- `local`: graph memory disabled by default unless explicitly configured;
- `docker-dev`: real Neo4j server required;
- `production`: real Neo4j server required.

Health diagnostics expose only `graph_memory=neo4j` (or `disabled` locally); secrets and credential-bearing URIs are never returned.

## Seed

The development seed contains Driver `driver-li`, Vehicle `vehicle-cold-a` with `status=normal`, Routes `xinping-road` and `national-102`, Weather `rain`, Anomaly `rain-slippery`, and Resolution `reroute-national-102`. It creates only the approved relations: `DRIVES`, `HAS_RISK_ON`, `HIGH_RISK_WHEN`, `ALTERNATIVE_TO`, and `RESOLVED_BY`. Running it twice changes neither entity nor relation counts.

## Testing and acceptance

Unit tests cover domain validation, Cypher allowlists, protocol behavior, deterministic extraction, service recall, bounded multi-hop paths, agent degradation, JSON serialization, topology, event mapping, settings, and frontend lifecycle/display. The integration script starts from a real Neo4j server, bootstraps schema, seeds twice, checks counts, writes and recalls facts, validates the three required relationship contexts, and records 20 warm-query min/avg/p95/max timing.

Full regression includes backend Ruff and pytest, frontend lint/test/build, `scripts/check.ps1`, Docker Compose config/build/up/status, Graph integration smoke, existing V1 core E2E, secret scan, and Git diff checks. V1 expected results remain `memory-rain-li`, `national-102`, `REROUTE`, unique dispatch, `APPROVED`, and zero pending messages.

