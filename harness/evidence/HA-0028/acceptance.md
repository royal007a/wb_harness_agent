# HA-0028 implementation evidence

## Passed

- A package may only be registered from a bounded `application/zip` body with `manifest.json` and `entry.py`; directory entries, links, path traversal, extra files, oversized files, invalid manifests and credential-shaped content are rejected.
- Registration copies immutable content to a controlled directory and records a SHA-256. Re-registering identical content is safe; execution recomputes the digest and rejects tampering instead of overwriting or running it.
- `HARNESS_EXTERNAL_SKILLS` is disabled by default. The execution endpoint returns `EXTERNAL_SKILL_RUNTIME_DISABLED` before it reads a package or invokes Docker.
- When explicitly enabled, the fixed image/runner run only a JSON object transform in a newly created and removed Colima container. The result audit includes package/input/output hashes, image/profile hashes, duration and cleanup status; third-party stdout/stderr/stack traces are not returned.
- The real opt-in probe confirmed uid `65532`, no network connection, no `/Users/weberzhao`, no Docker socket and no inherited environment sentinel. Full opt-in suite: 197 passed, 0 failed. Default verifier: 185 passed, 12 intentionally skipped, 0 failed.

## Non-goals retained

This is a single-user local JSON-transform boundary only. It has no package marketplace, signature/SBOM/license verification, URL/Git/pip/npm source, network, dynamic dependency, model, MCP, external data, Product Task/Run linkage or multi-tenant production claim. TD-018 and TD-027 remain open for those boundaries.
