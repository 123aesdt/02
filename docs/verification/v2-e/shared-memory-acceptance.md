# V2-E Shared Memory Acceptance

Status: **PASS**

- Real MySQL + Qdrant + Neo4j covered CREATE, MERGE, REPLACE, REJECT, CONFLICT_REVIEW, NOOP, low confidence, and expiry.
- Projection visibility: STAGED Qdrant leaks 0; STAGED Neo4j leaks 0; ACTIVE only visible; RETIRED not visible.
- Both partial directions recovered from PARTIAL to APPLIED while preserving the old canonical fact.
- Finalizing crash/resume succeeded; duplicate Qdrant points 0; duplicate Neo4j relations 0.
- Twenty same-version writer races: lost updates 0; each round had one Redis-lock/MySQL-CAS winner.
- Real browser outage test additionally stopped Qdrant, observed PARTIAL, restarted it, resumed the same mutation, and observed APPLIED.

Evidence: [shared-memory.json](raw/shared-memory.json), [browser E2E](raw/browser-e2e.json).
