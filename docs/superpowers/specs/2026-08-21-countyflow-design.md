# CountyFlow AI Design Specification

## Approved decisions

- Architecture: modular monolith, with separate FastAPI and asynchronous Worker deployments.
- Runtime path: Frontend → FastAPI → Redis Streams → Worker → LangGraph → MySQL/Qdrant/external APIs → WebSocket/status → Frontend.
- Provider boundary: separate `LLMProvider` and `EmbeddingProvider`; only OpenAI-Compatible production adapters in the first release; fake adapters only in tests.
- Persistence: MySQL is business truth. Redis is streams/short-lived coordination/checkpoints. Qdrant is vector Entity-Relation memory.
- Concurrency: SQLAlchemy `version_id_col` is mandatory for dispatch changes.
- UX: dark, restrained, enterprise AI logistics control room; the intelligent-dispatch detail is the focal page.

## Functional contract

An API request validates an anomaly, creates or returns an idempotent task, publishes it to a Redis Stream, and returns without waiting for the graph. A worker consumes it from a consumer group, applies the seven-node graph in order, writes durable results, acknowledges the message, and sends safe status events. A failure is classified as validation, retryable infrastructure/provider, concurrency conflict, or manual-review outcome; it is visible in task and audit data.

The graph state has the required identity, anomaly, environment, capacity, memory, candidate route, decision, fallback, dispatch version, audit, and timestamp fields, all modeled by typed substructures. Entity memory is genuine vector retrieval over historical resolution text plus entity context, returning id, score, resolution, and metadata. Routing visibly cites adopted historical evidence.

External weather/road calls use async `httpx`, a 0.8s target timeout, normalized exceptions, a circuit breaker, and static-rule fallback. Fallback usage and cause persist in graph/audit/status output. LLM and embedding calls receive the same timeout/error discipline under independently configured endpoints/models.

## Non-functional contract

Every service will gain a health check; worker restart policy is `unless-stopped`; dependencies use health-aware Compose conditions. Secrets are environment-only. Tests use fake models but real Redis/MySQL/Qdrant for integration behavior. Locust measures baseline endpoints separately from model inference. The project must offer `make check`, `make test`, `make lint`, `make up`, and `make down`.

## Detailed source of truth

The complete module boundaries, data model, stream semantics, UI system, deployment plan, and test matrix are in [../../design.md](../../design.md). That document is normative for implementation details; this specification locks the choices and scope for the plan below.

## Scope exclusions

No synchronous full-graph API execution, fake production Redis/locks/vector retrieval, broad provider catalog, microservice platform, RPC, service discovery, Kubernetes, complex message bus, or fabricated test/benchmark/deployment results.
