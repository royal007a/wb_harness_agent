# HA-0034 acceptance

## Result

Accepted as a deterministic **as-of temporal safety** correction for M1 Recall and M2-A Context/Detail. It is not a new semantic retrieval or Agent-memory capability.

## Contract and behavior

- Every Source-backed Fact read path now shares canonical visibility checks: same Bank, active Source/Fact, Source `occurred_at` at or before `as_of`, unexpired retention, Fact `occurred_at` at or before `as_of`, and matching Fact validity window.
- FTS5 only supplies M2-A candidates; it cannot bypass canonical time/status filtering.
- Future/invalid/cross-Bank IDs are `empty` or unavailable rather than evidence of non-existence. No path returns raw Source content.

## Verification

- New tests cover future Source, future Fact on a current Source, Recall/Context/Detail behavior, non-leakage, visibility after time advances, and restart.
- Full final opt-in regression: **223 passed, 0 failed**, with one upstream TestClient deprecation warning.
- New temporal synthetic evaluation and existing M2-A/M3-A/M3-B evaluations all passed; model/external calls were zero.
- Local and public runtime each declare the three `as_of_visibility` gates. Public systemd health, `pip check`, nginx syntax and unauthenticated `401` passed.

## Deployment safety

- Local SQLite backup: `.local/backups/pre-ha0034-20260920T175017Z.db`.
- Public SQLite online backup: `/var/lib/harnessagent/backups/pre-ha0034-20260920T175103Z.db`.
- Public promotion used staging and explicitly preserved the remote virtual environment, `.local` and prior Evidence.
