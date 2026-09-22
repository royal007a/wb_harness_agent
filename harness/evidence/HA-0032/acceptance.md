# HA-0032 acceptance

## Passed

- M3-A uses only caller-explicit Entity and Relation records, each bound to an active, same-Bank support Fact. There is no automatic Entity extraction, alias matching, model call, source-text inspection or natural-language GraphQA.
- `:graph-recall` accepts a known entity ID and traverses at most two active relation hops. Every returned edge contains the support Fact plus its Source ID/ref/SHA-256; Source content is not emitted. It filters Source, Fact, Entity, Relation, validity and occurrence time before traversal.
- Fact supersede/retract invalidates dependent graph objects; Source delete physically clears graph objects whose supporting Fact or endpoint was deleted. Synthetic evaluation covers two-hop provenance, before/after temporal filtering, cross-Bank zero leakage, retract/delete propagation and source-redaction.
- Full opt-in regression passed: 215 tests, 0 failed. Both M2-A and M3-A synthetic evaluators passed with model and external calls at zero.
- Local launchd was backed up and restarted before remote deployment. Local health, `memory-plane-m3a@1`, graph runtime declaration and three graph OpenAPI paths passed.
- The remote SQLite database was backed up before service stop. The remote systemd service is active; health, `memory-plane-m3a@1`, graph runtime declaration, three graph OpenAPI paths and an unknown-Bank graph route probe passed. Nginx configuration passed with only the pre-existing duplicate MIME warning; unauthenticated public access remains HTTP 401.

## Remote-release safety

Remote SSH intermittently timed out during preflight, before any remote service stop or source copy; the public proxy remained reachable. Once SSH was reachable, release promotion used target-side `rsync --delete` exclusions for `.venv/`, `.local/` and `harness/evidence/`. The remote virtual environment remained present and `pip check` passed. No local SQLite, Keychain, test data, HTTP Basic password or other secret was copied or recorded.

## Boundaries retained

M3-A is not a complete graph database, Hindsight integration, semantic/vector RAG, automatic Entity Resolution, natural-language GraphQA, graph ranking, model context injection, Reflect, multi-tenant identity system or a source of truth. A graph `empty` response only means no currently accessible, valid explicit evidence path; it never proves no business impact.
