# AMap published route verification — 2026-09-15

## Outcome

The original road-block failure had two independent causes:

1. `incident_node_id` / `affected_edge_id` were not preserved through every asynchronous boundary, so the graph could lose the exact blocked edge.
2. The live Docker fleet had V-002 in the valid current-task state `IN_TRANSIT`, but `FleetCapacityProvider` accepted only `AVAILABLE`. That converted a route-only incident into `UNAVAILABLE → MANUAL_REVIEW`.

The final behavior preserves `E04`, treats the current in-transit vehicle as eligible to continue a route-only dispatch, excludes `E04` through local Decimal Dijkstra, persists the selected route plus real-road evidence, automatically publishes an approved decision, and renders the assigned employee's route on AMap.

## Provider boundary

- Business orders, vehicles, drivers, road-network decisions, and the blocked edge remain repository-owned virtual demo data.
- Local Dijkstra remains the safety authority and selects the route before AMap is called.
- `AMAP_WEB_SERVICE_KEY` is not configured in the verified Docker runtime, so the backend returns bounded `CLIENT_MATCH_REQUIRED` waypoint evidence instead of blocking or sending the task to manual review.
- Existing `VITE_AMAP_KEY` and `VITE_AMAP_SECURITY_CODE` were injected into the frontend build without printing their values. AMap JS API then road-matched the persisted waypoints in the employee browser.
- If AMap JS is unavailable, the employee still receives the published local route diagram and driving instruction; the map provider never chooses a different business route.

## Fresh verification evidence

| Check | Actual result |
|---|---|
| Red regression: `test_capacity_provider.py` before the fix | 1 failed, 1 passed; `IN_TRANSIT` was incorrectly false |
| Targeted backend: capacity provider + API end-to-end + SQLAlchemy graph | 13 passed |
| Backend Ruff | `All checks passed!` |
| Backend full pytest | 1073 passed, 12 explicitly skipped, 1516 warnings, 369.46s |
| Frontend ESLint | exit 0; 0 errors, 2 pre-existing Fast Refresh warnings |
| Frontend Vitest | 69 files passed, 322 tests passed |
| Frontend production build | exit 0; 1962 modules transformed |
| Docker migration | exit 0 against healthy MySQL/Redis/Qdrant/Neo4j dependencies |
| Real Redis integration | 5 passed |
| Real four-store shared-memory integration | 1 passed |
| Real Docker + AMap Playwright flow | 1 passed; final accepted run 8.2s, suite 9.1s |

The browser assertion covers: employee-owned report acceptance, automatic terminal publication, visible “调度路线已发布”, route-map state `READY`, visible “高德道路已匹配”, mileage/time/validation/publication facts, driving instruction, drag/wheel interaction, absence of `runtime:read`, no unexpected 4xx/5xx response, no page error, and no mobile horizontal overflow.

Screenshot: `docs/verification/screenshots/amap-published-driver-route.png`.

## Known non-blocking verification debt

An earlier opt-in extended MySQL suite run reported 25 passed and 3 fixture failures: one obsolete seed row-count expectation and two concurrency fixtures missing FleetVehicle foreign-key parents. It was run before the final one-line `IN_TRANSIT` provider fix and is not counted as green final evidence. The required full suite and targeted live Redis/four-store integrations above are green.
