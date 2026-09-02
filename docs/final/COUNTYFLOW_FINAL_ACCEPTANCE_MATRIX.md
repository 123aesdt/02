# CountyFlow 最终验收矩阵

> 事实源：[FINAL_FACTS.md](./FINAL_FACTS.md)
> 审计日期：2026-08-31
> 状态只使用 VERIFIED、NOT VERIFIED、NOT EXPOSED、DEFERRED。历史证据在 Evidence 中明确标注，不冒充本轮在线结果。

## 1. 状态说明

| Status | 判定规则 |
|---|---|
| VERIFIED | 当前代码/配置可直接确认，或本轮实际命令通过 |
| NOT VERIFIED | 能力/历史证据存在，但本轮运行条件不足以重新确认 |
| NOT EXPOSED | 能力或数据存在，但当前用户界面/公共 read model 未暴露 |
| DEFERRED | 没有生产实现与验收证据，明确延期 |

## 2. 核心架构

| Feature | Status | Evidence | Metric | Test | Verification Path |
|---|---|---|---|---|---|
| FastAPI API boundary | VERIFIED | 路由与 service 分层存在 | health + v1 routes | backend API tests | `backend/app/main.py`, `backend/app/api/v1/` |
| Async task creation | VERIFIED | handler 创建 task 后 XADD，不同步跑图 | HTTP 202 | dispatch API tests | `backend/app/services/dispatch_task_api_service.py` |
| Redis Streams queue | VERIFIED | XADD/XREADGROUP/XACK/XAUTOCLAIM 实现 | bounded retry 3 | stream/worker tests | `backend/app/streams/redis_queue.py` |
| Dual Worker declaration | VERIFIED | compose 声明 worker-1/worker-2 | 2 workers | compose config parsed | `docker-compose.yml` |
| Live dual Worker execution | NOT VERIFIED | 历史容器证据存在；本轮 daemon 不可用 | historical recovery ≤5 s | real Redis skips not rerun | `docs/verification/` |
| LangGraph execution | VERIFIED | 图编译与固定节点顺序 | 8 agents | graph unit/integration tests | `backend/app/graph/builder.py` |
| LLM Provider abstraction | VERIFIED | Protocol + OpenAI-Compatible implementation | timeout 10 s default | provider unit tests | `backend/app/providers/llm/` |
| LLM used by current graph | DEFERRED | GraphDependencies 未注入 LLM | 0 graph LLM calls | source audit | `backend/app/graph/dependencies.py` |
| Production runtime wiring | DEFERRED | production profile 主动抛错 | no production provider graph | runtime tests | `backend/app/runtime.py` |

## 3. Agent

| Feature | Status | Evidence | Metric | Test | Verification Path |
|---|---|---|---|---|---|
| Intake Agent | VERIFIED | 校验、规范化、人工复核 | position 1/8 | intake tests | `backend/app/agents/intake.py` |
| Entity Memory Agent | VERIFIED | Qdrant top-3 与失败降级 | position 2/8 | memory agent tests | `backend/app/agents/memory.py` |
| Graph Memory Agent | VERIFIED | Neo4j facts/paths 与降级 | position 3/8 | graph-memory tests | `backend/app/agents/graph_memory.py` |
| Environment Agent | VERIFIED | timeout/circuit breaker/fallback | position 4/8 | environment tests | `backend/app/agents/environment.py` |
| Capacity Agent | VERIFIED | vehicle status 与容量评估 | position 5/8 | capacity tests | `backend/app/agents/capacity.py` |
| Routing Agent | VERIFIED | candidates/recommendation/memory adoption | position 6/8 | routing tests | `backend/app/agents/routing.py` |
| Dispatch Agent | VERIFIED | optimistic-lock dispatch write | position 7/8 | dispatch tests | `backend/app/agents/dispatch.py` |
| Audit Agent | VERIFIED | durable evidence，失败阻止安全 ACK | position 8/8 | audit/worker tests | `backend/app/agents/audit.py` |

## 4. Runtime 与一致性

| Feature | Status | Evidence | Metric | Test | Verification Path |
|---|---|---|---|---|---|
| Runtime Thread registry | VERIFIED | MySQL metadata/current pointer/event history | versioned row | runtime thread tests | `backend/app/runtime_threads/` |
| Redis checkpointer | VERIFIED | AsyncRedisSaver adapter | TTL 10080 min; max 1 MiB | unit tests | `backend/app/runtime_threads/checkpoint_store.py` |
| Real Redis checkpoint recovery | NOT VERIFIED | 历史 5/5；本轮 2 real tests skipped | max 4.579 s historical | Docker daemon unavailable | `docs/verification/v2-e/` |
| N+1 resume | VERIFIED | runner validates next node and ancestry | intake → entity_memory | runner tests | `backend/app/runtime_threads/runner.py` |
| Runtime optimistic locking | VERIFIED | `version_id_col` + stale conflict | no Python equality emulation | concurrency tests | `backend/app/models/runtime_thread.py` |
| Runtime Override boundary | VERIFIED | environment → capacity only | supported vehicle transitions 3 | policy tests | `backend/app/runtime_overrides/policy.py` |
| Runtime Override pipeline | VERIFIED | lock/CAS/aupdate_state/promotion/audit | historical 50/50 legal | override tests | `backend/app/runtime_overrides/service.py` |
| Runtime Override live race | NOT VERIFIED | 历史竞态证据；本轮 Docker 未跑 | 20 unique winners; 50 boundary races | historical acceptance | `docs/verification/v2-e/` |
| Override PARTIAL reconciliation | VERIFIED | reconciler 实现与测试 | resumable status | reconciler tests | `backend/app/runtime_overrides/reconciler.py` |
| Dispatch optimistic locking | VERIFIED | SQLAlchemy versioned row | historical 20/20 conflicts | concurrency tests | `backend/app/models/dispatch.py` |
| Effectively-once business effect | VERIFIED | lock + ledger + terminal ACK | duplicate business writes 0 historical | worker/idempotency tests | `backend/app/workers/dispatch_worker.py` |
| Exactly-once delivery claim | DEFERRED | 系统不提供数学意义 exactly-once | not claimed | architecture audit | `docs/final/FINAL_FACTS.md` |

## 5. Memory

| Feature | Status | Evidence | Metric | Test | Verification Path |
|---|---|---|---|---|---|
| Qdrant repository | VERIFIED | cosine collection/payload/filter/query | collection `entity_resolution_memory` | repository tests | `backend/app/memory/qdrant_repository.py` |
| Docker real embedding | DEFERRED | compose 明确使用 fake | dimension 128 configured | runtime tests | `docker-compose.yml` |
| Real embedding benchmark | NOT VERIFIED | 2026-08-27 原始证据 | Top-1 98%; Top-3 100% | benchmark historical | `docs/verification/v2-e/` |
| Neo4j graph repository | VERIFIED | schema/upsert/facts/multi-hop | 11 entity; 10 relation | graph repository tests | `backend/app/graph_memory/` |
| Live Neo4j recall | NOT VERIFIED | 历史 recall 20/20 + 20/20 | P95 10.354 ms | Docker daemon unavailable | `docs/verification/v2-e/` |
| Shared Memory canonical control plane | VERIFIED | MySQL fact/mutation/evidence/attempt | 6 decisions | shared-memory tests | `backend/app/shared_memory/` |
| Projection lifecycle | VERIFIED | staged/finalize/active/retire | leak 0 historical | projection tests | `backend/app/shared_memory/service.py` |
| PARTIAL recovery | VERIFIED | Qdrant/Neo4j failure resume | PARTIAL → APPLIED historical | reconciler tests | `backend/app/shared_memory/reconciler.py` |
| Shared Memory live race | NOT VERIFIED | historical 20 rounds no lost update | lost update 0 | real race skipped | `docs/verification/v2-e/` |
| Canonical truth in Qdrant/Neo4j | DEFERRED | 明确不是设计目标 | projections only | source audit | `backend/app/shared_memory/sqlalchemy_repository.py` |

## 6. Security

| Feature | Status | Evidence | Metric | Test | Verification Path |
|---|---|---|---|---|---|
| AuthenticatedPrincipal | VERIFIED | subject/roles/permissions/claims | 6 roles | auth tests | `backend/app/security/models.py` |
| Development JWT | VERIFIED | HS256 + min 32 chars | claim validation | JWT tests | `backend/app/security/jwt_provider.py` |
| OIDC/JWKS boundary | VERIFIED | RS256/ES256 allowlist + cache/timeout | issuer/audience/time/jti | OIDC tests | `backend/app/security/jwt_provider.py` |
| Production OIDC deployment | NOT VERIFIED | code boundary存在；未接真实 IdP | no live issuer test | Docker daemon/offline | `.env.example` |
| RBAC | VERIFIED | endpoint permission dependencies | 6 roles | role security tests | `backend/app/security/permissions.py` |
| Rate Limit | VERIFIED | Redis token bucket + fail-closed writes | per-operation quotas | rate-limit tests | `backend/app/security/rate_limit.py` |
| Token revocation | VERIFIED | Redis revocation store | jti/expiry | revocation tests | `backend/app/security/revocation.py` |
| Security Audit | VERIFIED | durable SQL repository | event taxonomy | audit tests | `backend/app/security/security_audit.py` |
| Sensitive redaction | VERIFIED | bearer/basic/JWT/URL/query/key patterns | historical scan 0 findings | redaction tests | `backend/app/security/redaction.py` |
| Current live secret scan | NOT VERIFIED | 本轮未读取真实 secret values | historical 838×6, 0 | historical artifact scan | `docs/verification/frontend-role-ui/` |
| Security headers/CORS/body limit | VERIFIED | middleware/config | production HSTS conditional | HTTP security tests | `backend/app/security/http.py` |
| WS single-use ticket | VERIFIED | digest/TTL/GETDEL/scope | TTL 45 s | WS security tests | `backend/app/security/ws_ticket.py` |
| Security ON performance | NOT VERIFIED | 2026-08-29 历史 raw evidence | QPS 278.998; P95 270 ms | historical Locust | `docs/verification/v2-g2/raw/` |

## 7. Frontend

| Feature | Status | Evidence | Metric | Test | Verification Path |
|---|---|---|---|---|---|
| White enterprise App Shell | VERIFIED | 最终 CSS override 与组件结构 | responsive breakpoints | Vitest/build; historical browser | `frontend/src/` |
| Live browser visual state | NOT VERIFIED | 本轮未运行 Playwright | 14 specs exist | historical suites passed | `frontend/e2e/` |
| Dispatcher Workspace | VERIFIED | 真实 task buckets | pending/running/completed | frontend tests | `frontend/src/features/` |
| Supervisor Workspace | VERIFIED | review + runtime summary | real read models | frontend tests | `frontend/src/features/` |
| Operator Operations | VERIFIED | observability/runtime summary | live API semantics | frontend tests | `frontend/src/features/` |
| Auditor Audit | VERIFIED | security audit read | paged events | frontend tests | `frontend/src/features/` |
| Admin Overview | VERIFIED | real workspace counts | real overview | frontend tests | `frontend/src/features/` |
| My Tasks | VERIFIED | employee-assigned task read | EMPLOYEE role | frontend/API tests | `frontend/src/`, `backend/app/api/v1/workspace_reads.py` |
| Team Tasks | NOT EXPOSED | route intentionally shows state | no team data API exposed | route tests | `frontend/src/app/router.tsx` |
| Global intervention history | NOT EXPOSED | Supervisor 仅有 summary/current reads | no global view | source audit | `frontend/src/` |
| Full Auditor business/memory/override history | NOT EXPOSED | 当前只暴露 security audit 等 | partial product scope | source audit | `frontend/src/` |
| Runtime checkpoint body | NOT EXPOSED | UI/API 仅提供安全 metadata | no raw state leak | runtime read tests | `backend/app/api/v1/runtime_threads.py` |
| API mode no mock fallback | VERIFIED | truth-state architecture | explicit UNAVAILABLE | frontend tests | `frontend/src/` |
| Frontend unit tests | VERIFIED | 本轮实际执行 | 49 files; 228 pass | Vitest | `frontend/src/**/*.test.*` |
| Frontend lint | VERIFIED | 本轮 exit 0 | 0 error; 2 warnings | ESLint | `frontend/` |
| Frontend build | VERIFIED | 本轮 Vite build | 1915 modules | Vite | `frontend/dist/` |

## 8. Observability

| Feature | Status | Evidence | Metric | Test | Verification Path |
|---|---|---|---|---|---|
| Metrics catalog | VERIFIED | 当前代码统计 | 46 families | catalog tests | `backend/app/observability/catalog.py` |
| Recording rules | VERIFIED | 当前 YAML 统计 | 9 | rule tests/scans | `monitoring/prometheus/` |
| Alert rules | VERIFIED | 当前 YAML 统计 | 18 | rule tests/scans | `monitoring/prometheus/` |
| Prometheus service | VERIFIED | compose declaration/config | image 3.5.0 | compose config | `docker-compose.yml` |
| Grafana service | VERIFIED | provisioning/config | image 12.1.0 | compose config | `monitoring/grafana/` |
| Live metrics and dashboards | NOT VERIFIED | Docker daemon unavailable | historical screenshots/evidence | historical browser/E2E | `docs/verification/v2-g1/` |
| Alert lifecycle | NOT VERIFIED | 历史 Neo4j pending/firing/resolved | for=2m | historical failure injection | `docs/verification/v2-g1/` |
| Failure isolation | NOT VERIFIED | 历史 Neo4j/Worker/Prometheus/Grafana evidence | business continuity observed | historical E2E | `docs/verification/v2-g1/` |
| API SLO | VERIFIED | rule/spec/code一致 | P95<300ms, 5xx<0.1% | rule tests | `docs/slo.md`, `monitoring/` |
| Graph SLO latest raw sample | NOT VERIFIED | historical raw P95 167.311ms | target <150ms, sample over target | historical run | `docs/verification/v2-g1/raw/` |

## 9. Docker 与基础设施

| Feature | Status | Evidence | Metric | Test | Verification Path |
|---|---|---|---|---|---|
| Compose syntax/config | VERIFIED | 本轮 config --services 成功 | 11 declared | docker compose config | `docker-compose.yml` |
| Long-running topology | VERIFIED | 11 less migration | 10 long-running | static config | `docker-compose.yml` |
| Named volumes | VERIFIED | compose declarations | 6 | static config | `docker-compose.yml` |
| Networks | VERIFIED | default + host_access | 2 | static config | `docker-compose.yml` |
| Current container health | NOT VERIFIED | Docker daemon unavailable | historical 10 running | ps failed this audit | local Docker host |
| Migration | VERIFIED | Alembic upgrade + seed one-shot | 10 revisions | migration tests/static | `backend/alembic/versions/` |
| MySQL canonical storage | VERIFIED | models/repositories/migrations | MySQL 8.4 image | persistence tests | `backend/app/models/` |
| Redis runtime | VERIFIED | stream/checkpoint/lock/security wiring | Redis 8.2.9 image | unit tests/static | `docker-compose.yml` |
| Qdrant runtime | VERIFIED | compose + repositories | cosine collection | repository tests | `docker-compose.yml` |
| Neo4j runtime | VERIFIED | compose + repository/schema | Neo4j 5.26 | repository tests | `docker-compose.yml` |

## 10. Testing 与性能

| Feature | Status | Evidence | Metric | Test | Verification Path |
|---|---|---|---|---|---|
| Ruff | VERIFIED | 本轮执行通过 | ACL warnings only | ruff check backend | `backend/` |
| Default backend pytest entry | NOT VERIFIED | 当前 `.env` secret 太短导致 15 collection errors | 0 completed in default run | pytest | local ignored `.env` |
| Isolated backend pytest | VERIFIED | 本轮进程级 auth disabled | 833 pass; 7 skip; 703 warnings | pytest | `backend/tests/` |
| Real dependency skipped tests | NOT VERIFIED | 7 skips中涉及 Redis/MySQL/race | 7 | pytest skip report | `backend/tests/` |
| Browser E2E | NOT VERIFIED | 14 specs；本轮未执行 | historical 1+6+7+1 pass groups | Playwright | `frontend/e2e/` |
| V2-E black box | NOT VERIFIED | 历史原始证据 | 15/15; pending 0 | historical acceptance | `docs/verification/v2-e/` |
| V2-E Locust | NOT VERIFIED | 历史 3×60s 50 users | min QPS400.071; max P95200ms; error0 | Locust | `docs/verification/v2-e/raw/` |
| Observability ON performance | NOT VERIFIED | 2026-08-29 raw | QPS1037.85; API P9566.022ms; error0 | historical benchmark | `docs/verification/v2-g1/raw/` |
| DR E2E | DEFERRED | 无脚本/测试/证据 | none | none | no V2-G3 directory |

## 11. Disaster Recovery

| Feature | Status | Evidence | Metric | Test | Verification Path |
|---|---|---|---|---|---|
| MySQL backup automation | DEFERRED | 未发现生产脚本 | none | none | repository audit |
| Redis recovery backup set | DEFERRED | AOF 可靠性证据不等于 DR | none | none | repository audit |
| Qdrant snapshot workflow | DEFERRED | 未发现 snapshot/restore | none | none | repository audit |
| Neo4j backup workflow | DEFERRED | 未发现 backup/restore | none | none | repository audit |
| Backup manifest/checksum | DEFERRED | 未发现实现 | none | none | repository audit |
| Secret sanitizer | DEFERRED | 未发现 DR sanitizer | none | none | repository audit |
| Restore order/reconciliation | DEFERRED | 无跨存储恢复编排 | none | none | repository audit |
| RPO/RTO measurement | DEFERRED | 无指标和 drill | none | none | repository audit |
| DR frontend readiness | DEFERRED | 无 DR 状态 read model | none | none | repository audit |

## 12. 最终验收判断

CountyFlow 的核心工程原型是 VERIFIED：异步任务、8-Agent、Runtime Thread、Checkpoint、Runtime Override、Shared Memory、RBAC、安全审计、白色多角色 UI 与可观测配置均有当前实现。

生产验收不能判 COMPLETE：真实 Provider wiring、完整 Docker 实时重验、生产 IdP、所有真实依赖 integration、当前浏览器 E2E、当前性能门禁和灾备均未形成同一批次的最终生产证据。最终状态为“工程化智能调度原型已完成，生产化与灾备未完成”。
