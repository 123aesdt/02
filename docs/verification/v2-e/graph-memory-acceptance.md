# V2-E Graph Memory Acceptance

Status: **PASS**

- Entity allowlist coverage: Driver, Vehicle, Route, Weather, RoadCondition, Station, Anomaly, Resolution.
- Required relation coverage: DRIVES, HAS_RISK_ON, HIGH_RISK_WHEN, ALTERNATIVE_TO, STATUS, RESOLVED_BY.
- Deterministic extraction: 3/3 entity sets and 3/3 relation sets exact; all persisted to real Neo4j.
- Structured recall: 20/20 facts and 20/20 expected paths, including `driver-li -> xinping-road -> national-102`.
- Warm retrieval: 50 samples; min 5.357ms, avg 7.808ms, p95 10.354ms, max 12.632ms.

Evidence: [graph-memory.json](raw/graph-memory.json), [queries CSV](raw/graph-memory-queries.csv), [timings CSV](raw/graph-memory-timings.csv).
