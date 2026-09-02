# V2-E Runtime Override Acceptance

Status: **PASS**

- Legal stable-boundary overrides: 50/50 APPLIED.
- Next Capacity read new BROKEN state: 50/50; stale downstream reads 0.
- Stale expected versions: 20/20 rejected; silent overrides 0.
- Concurrent actors: 20/20 exactly one APPLIED and one safe conflict; state version increased once.
- Worker-boundary vs override-boundary races: 50, invariant violations 0.
- Timing total: min 120.532ms, avg 144.998ms, p95 181.643ms, max 247.588ms.
- Lock TTL 8000ms; measured required bound 2247.588ms.
- Browser API mode: 7/7 scenarios, no unexpected or flaky tests.

Evidence: [runtime-override.json](raw/runtime-override.json), [browser E2E](raw/browser-e2e.json), [override recovery](raw/override-worker-recovery.json).
