# V2-E Checkpoint Acceptance

Status: **PASS**

- Official Redis 8 checkpointer: 20/20 exact reads; errors 0.
- Write p95 11.468ms; exact-read p95 2.760ms; maximum payload 605 bytes in the focused boundary benchmark.
- Canonical pointer, append-only history, state version, orphan isolation, exact resume, and N+1 resume were verified.
- Five crash/resume trials resumed the observed checkpoint at N+1, promoted all eight nodes once, produced one dispatch and one audit, and left Pending=0.
- Five override + worker-kill trials resumed from the override-promoted canonical checkpoint; Capacity still read BROKEN and terminal state was REVIEW_REQUIRED.

Evidence: [checkpoint.json](raw/checkpoint.json), [checkpoint recovery](raw/checkpoint-recovery.json), [override recovery](raw/override-worker-recovery.json).
