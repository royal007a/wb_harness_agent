# HA-0030 deployment evidence

## Passed

- The project map and Operations policy now require deployment changes to validate local `127.0.0.1:8765` first, then the existing public `systemd`/nginx topology, unless the user explicitly opts out.
- The local launchd service passed health and the HA-0028 external Skill runtime remained disabled, network-denied and credential-free. HA-0029 Memory Plane M1 was available with explicit source/fact retention only.
- Before remote synchronization, an online SQLite backup was created. The staged copy excluded local database files, Keychain material, virtualenv, test data and local Evidence. The remote service passed Python syntax checks, restarted active, and nginx configuration validation passed.
- The remote loopback health endpoint and both HA-0028/HA-0029 runtime endpoints passed. Their safety gates remain closed. Matching SHA-256 digests for six changed contracts/runtime files are recorded in `deployment.json`.
- The public HTTPS proxy continues to return `401` when no HTTP Basic credential is supplied. No credential was read, changed or recorded during this deployment.
- Final local default verification: 191 passed, 12 intentionally skipped, 0 failed; one upstream deprecation warning.

## Boundaries retained

This is a deployment of local single-user control-plane slices, not proof of a production multi-tenant Agent platform, a real model/Claude workflow, authenticated end-user flow, external Skill execution, or a live investment-research system.
