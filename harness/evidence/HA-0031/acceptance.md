# HA-0031 acceptance

## Passed

- Explicit canonical Source/Fact remains the only persistent memory input. `:context` builds a bounded, typed Fact Capsule from active same-Bank Facts and caller-supplied recent turns remain transient; `:recall-details` revalidates Bank, Source, lifecycle and time before returning compact Fact detail.
- SQLite FTS5 is a rebuildable keyword-only projection, not a semantic/vector index. Supersede, retract and delete remove or filter candidates; raw Source content is not emitted by either M2-A response.
- Full opt-in regression passed: 209 tests, 0 failed. The deterministic synthetic evaluator passed all declared capsule/detail/lifecycle/isolation/privacy measures; its limits are retained in `manifest.json`.
- Local launchd was backed up and restarted before remote deployment. Local health, `memory-plane-m2a@1`, FTS5 readiness and both new route probes passed without creating test memory records.
- The remote SQLite database was backed up before service stop. The remote systemd service is active; loopback health, `memory-plane-m2a@1`, FTS5 readiness and both new route probes passed. Nginx configuration passed with only the pre-existing duplicate MIME warning; unauthenticated public access remains HTTP 401.

## Deployment recovery and prevention

The first remote promotion command omitted live-target exclusions while using `rsync --delete`, deleting the remote virtual environment and briefly stopping the service. The database backup had completed and no business data or secret was copied. The environment was rebuilt from the pinned `requirements.txt`, syntax checked and the service recovered before final validation. `AGENTS.md` and `OPERATIONS.md` now require target-side exclusions for `.venv/` and service-owned data; the incident is recorded in `deployment.json`.

## Boundaries retained

M2-A is not Hindsight production integration, complete RAG, semantic/graph retrieval, model summary, RRF/reranking, Reflect, automatic conversation ingestion, identity/multi-tenant isolation or a source of truth. The runtime continues to keep model/provider, network search, external finance data and external Skill execution disabled.
