# MySQL Concurrent Conflict Acceptance

Date: 2026-08-26. Runtime: MySQL 8.4 through SQLAlchemy `version_id_col`.

Twenty trials used two Sessions that loaded the same Dispatch version. Session A committed first; every stale Session B commit raised `StaleDataError`. The persisted winner was checked and each probe row was removed.

| Metric | Result |
|---|---:|
| Trials | 20 |
| Conflicts intercepted | 20 |
| Interception rate | 100% |
| Silent overwrites | 0 |

Raw evidence: `raw/concurrency-results.json`.
