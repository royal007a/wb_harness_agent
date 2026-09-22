# HA-0033 acceptance

## Result

Accepted as a **restricted local-admin M3-B exact Entity Catalog**. It is not accepted as automatic Entity Resolution, semantic retrieval, a knowledge graph, a complete Hindsight implementation, or an external-data/real-model integration.

## Contract and behavior

- `:resolve-entity` accepts canonical name or registered alias, optional type and time; its only matching rule is Unicode casefold exact equality.
- Results preserve `resolved`, `ambiguous`, and `not_found`. More than one exact candidate is never silently selected; Graph recall still needs an explicit Entity ID.
- Each returned candidate revalidates Bank, active Source/Fact/Entity and time, and returns only Fact statement plus Source ID/ref/SHA-256. It never returns raw Source content.
- Tests cover canonical and alias match, ambiguity, type filtering, cross-Bank non-leakage, sensitive/unknown input rejection, time, supersede, retract, delete, restart, OpenAPI and runtime capability declaration.

## Verification

- Full opt-in regression: **220 passed, 0 failed**, with one upstream TestClient deprecation warning; JUnit: `all-tests.xml`.
- M2-A context, M3-A graph and M3-B catalog synthetic evaluations passed with model/external call counts all zero.
- Both local and public runtime report `memory-plane-m3b@1`; their relevant source hashes match.
- Local launchd health, public systemd loopback health, runtime/OpenAPI/probe endpoint, `pip check`, nginx syntax and unauthenticated public `401` all passed.

## Deployment safety

- Local SQLite backup: `.local/backups/pre-ha0033-20260920T172807Z.db`.
- Public SQLite online backup: `/var/lib/harnessagent/backups/pre-ha0033-20260920T173106Z.db`.
- Public live promotion explicitly preserved `.venv/`, `.local/` and existing Evidence while using staging; no local data or secrets were copied to public infrastructure.
