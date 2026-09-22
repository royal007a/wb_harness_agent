# HA-0029 implementation evidence

## Passed

- M1 has strict machine contracts for local Bank, Source, Fact Retain and Evidence Bundle. Bank ownership is set server-side to `ws_local` / `local_admin`; callers cannot submit another workspace or owner.
- Retain accepts bounded explicit source content and atomic facts only. Every fact records source ID, classification, occurred/recorded/valid time, confidence and lifecycle state. No model extraction or chat dump occurs.
- Identical source content is deduplicated in a Bank, write actions are idempotent, a supersede keeps the old fact as `superseded`, and cross-Bank correction atomically fails without leaving a partial source/fact.
- Recall only reads one Bank, filters active/retention/valid-time state, ranks deterministic keyword/temporal matches, and returns a bounded Evidence Bundle with Source ID/ref/SHA-256 rather than raw source content.
- Retraction removes dependent facts from recall; deletion physically removes controllable source/fact text and keeps a no-content tombstone/audit. Persistence and expiry filtering survive a SQLite restart.
- Full opt-in suite: 203 passed, 0 failed. Default verifier: 191 passed, 12 intentionally skipped, 0 failed.

## Non-goals retained

M1 is not model memory automation, a vector/RAG system, entity graph, Reflect engine, authoritative fact store, DeepAgents integration or multi-tenant memory service. TD-028 records the remaining M2–M5 and identity/production work.
