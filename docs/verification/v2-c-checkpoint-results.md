# V2-C Persistent Checkpoint Verification

Status: **COMPLETE** on 2026-08-27 (Asia/Shanghai).

## Runtime and versions

- LangGraph `1.2.11`
- `langgraph-checkpoint` `4.2.0`
- official `langgraph-checkpoint-redis` `0.5.2`
- Python Redis client `6.4.0`
- Docker Redis image `redis:8.2.9-alpine`, AOF enabled
- Neo4j `5.26-community`, MySQL `8.4`, Qdrant Server
- Docker Compose service count: 9

MySQL remains canonical for task, dispatch, audit, and Runtime Thread metadata. Redis stores immutable LangGraph checkpoint payloads; Qdrant and Neo4j remain long-term vector and graph memory. No driver, session, repository, service, or checkpointer enters `DispatchGraphState`.

## Local regression

- `python -m ruff check backend`: PASS
- `python -m pytest backend/tests -q`: **413 passed, 3 skipped**, one third-party Starlette TestClient deprecation warning
- The three normal-suite skips are explicit Real Store opt-ins; the two real Redis saver tests separately passed **2/2** against Docker Redis 8, and the four-store behavior is covered by the Docker gate.
- `npm run lint`: PASS
- `npm test -- --run`: **40 passed** in 11 files
- `npm run build`: PASS

## Mandatory test traceability

| Test | Location | Result |
| --- | --- | --- |
| `test_thread_registry_create` | `backend/tests/runtime_threads/test_registry.py` | PASS |
| `test_thread_id_stable_across_worker_retry` | same | PASS |
| `test_checkpoint_after_node` | `backend/tests/runtime_threads/test_graph_checkpointing.py` | PASS |
| `test_checkpoint_payload_serializable` | same | PASS |
| `test_checkpoint_excludes_dependencies` | same | PASS |
| `test_checkpoint_history_append_only` | `backend/tests/runtime_threads/test_registry.py` | PASS |
| `test_current_checkpoint_pointer` | same | PASS |
| `test_state_version_increments` | same | PASS |
| `test_terminal_thread_marked` | same | PASS |
| `test_resume_from_latest_checkpoint` | `backend/tests/runtime_threads/test_resume.py` | PASS |
| `test_resume_does_not_repeat_completed_nodes` | same | PASS |
| `test_resume_no_duplicate_dispatch` | same | PASS |
| `test_resume_no_duplicate_audit` | same | PASS |
| `test_checkpoint_registry_partial_failure` | `backend/tests/runtime_threads/test_consistency.py` | PASS |
| `test_checkpoint_reconciliation` | same | PASS |
| `test_thread_read_api` | `backend/tests/api/test_runtime_threads.py` | PASS |
| `test_thread_history_api` | same | PASS |
| `test_production_runtime_api_requires_auth` | `backend/tests/unit/test_settings.py` | PASS |
| `test_checkpoint_event` | `backend/tests/runtime_threads/test_events.py` | PASS |

Additional regression coverage verifies fail-closed external authorization injection, DLQ canonical terminal persistence, terminal event ordering, per-delivery resume idempotency, namespace/JSON/size guards, bounded orphan reconciliation, startup saver setup, and frontend refresh behavior.

## Real Redis checkpoint evidence

The official AsyncRedisSaver real-server tests passed 2/2. The latest 20-write/20-exact-read run reported zero errors:

| Metric | Min | Average | P95 | Max |
| --- | ---: | ---: | ---: | ---: |
| synchronous write latency (ms) | 6.387 | 7.842 | 8.336 | 18.775 |
| exact read latency (ms) | 1.765 | 2.032 | 2.291 | 2.833 |
| serialized payload (bytes) | 598 | 600.45 | 604 | 605 |

Raw evidence: `docs/verification/raw/v2-c-checkpoint-performance.json`.

## Real two-worker crash recovery

Worker-1 was deterministically stopped after the canonical `intake` checkpoint. A warm Worker-2 reclaimed the pending Redis Stream message and resumed from the exact observed checkpoint. Each run executed `entity_memory` next; every one of the eight promoted nodes appeared exactly once.

| Run | Recovery (s) | Exact checkpoint | Dispatch | Audit | Pending | Result |
| ---: | ---: | --- | ---: | ---: | ---: | --- |
| 1 | 4.570 | yes | 1 | 1 | 0 | PASS |
| 2 | 4.222 | yes | 1 | 1 | 0 | PASS |
| 3 | 4.485 | yes | 1 | 1 | 0 | PASS |

All runs preserved `memory-rain-li → national-102 → REROUTE → APPROVED`, produced no V2-B memory mutation, and stayed below the accepted five-second recovery ceiling. Raw evidence: `docs/verification/raw/v2-c-checkpoint-recovery.json`.

## Full Docker and prior-phase regression

`scripts/test-docker.ps1` completed successfully against the nine-service stack. It verified Redis Streams, MySQL, Qdrant, Neo4j bounded Graph Memory, eight-agent WebSocket events, V2-B four-store mutation/reconciliation, official checkpoint persistence, three crash/resume trials, one dispatch, one audit, and final Pending 0.

The accepted V1/V2-A/V2-B evidence remains unchanged: real embedding Top-1 49/50 (98%), Locust three-run maximum error rate 0% and maximum P95 260 ms, graph evidence present, and the core routing/audit result preserved.

## Scope closure

V2-C adds only persistent checkpoint/thread foundations and read-only inspection. It does not add Runtime Override, checkpoint mutation/deletion, `update_state`, pause/resume command endpoints, rollback, target-node mutation, or memory merge. No code was committed.
