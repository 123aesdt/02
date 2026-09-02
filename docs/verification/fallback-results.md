# Fallback Acceptance

Date: 2026-08-26. A real Docker Worker called a controlled HTTP primary that delayed for 2 seconds. The provider timeout remained 0.8 seconds; the circuit threshold was set above the 10-run sample so every trial exercised the primary timeout rather than the open-circuit shortcut.

| Metric | Result |
|---|---:|
| Runs | 10 |
| Passed | 10 |
| Minimum | 801.112 ms |
| Average | 801.773 ms |
| P95 | 802.303 ms |
| Maximum | 802.303 ms |
| System-level errors | 0 |

Every Graph continued to `COMPLETED`, every result recorded `fallback_used=true` with the timeout reason, and every task had one approved Audit and one Dispatch. Raw evidence: `raw/fallback-results.json`.
