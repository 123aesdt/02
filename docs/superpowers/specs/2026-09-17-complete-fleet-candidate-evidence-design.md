# Complete Fleet Candidate Evidence Design

## Goal

Make every vehicle row in the dispatch candidate table explainable and presentation-ready without changing which vehicle is eligible or ultimately selected.

## Approved behavior

- Persist the complete candidate snapshot for every evaluated vehicle: driver, driver status, vehicle status, remaining load, gross weight, cargo capability, pickup route, pickup distance, pickup ETA, score, score components, eligibility, and exclusion reasons.
- Evaluate pickup travel and a comparison score for rejected vehicles whenever the pickup point is reachable. Eligibility remains controlled only by the existing hard constraints and delivery reachability checks.
- Preserve truthful unavailable states. A missing driver is shown as unassigned; an unreachable pickup is shown as unreachable and not scored, rather than as generic missing evidence.
- Rank only dispatchable vehicles. Rejected vehicles are labelled as excluded from ranking so comparison data does not imply that they could have been selected.
- Use deterministic backend/database evidence. Do not invent random values in the frontend.
- Keep existing selected-vehicle and reservation behavior unchanged.

## Data flow

`FleetAllocationService` evaluates every fleet snapshot and returns a complete `VehicleCandidate`. The capacity agent serializes the candidate once. `DispatchService` persists the same complete shape for every candidate in the `FLEET_ALLOCATION` evidence row. `DispatchTaskApiService` validates and returns that evidence, and `FleetAllocationPanel` renders explicit states instead of generic placeholders.

## Verification

- Backend service tests prove rejected-but-reachable vehicles retain pickup and scoring evidence.
- Dispatch persistence and task-detail API tests prove non-selected candidates keep all fields.
- Frontend component tests prove complete rows and explicit unreachable/not-ranked labels.
- Full lint, tests, build, diff check, Docker rebuild, and a real repeated demo dispatch confirm the behavior end to end.
