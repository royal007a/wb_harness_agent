# HA-0027 implementation evidence

## Passed locally

- `claude-agent-sdk==0.2.152` constructs a real in-process `research_sources` MCP server with `mcp==2.2.0` and the exact three native `AgentDefinition` objects.
- Parent options expose only `Agent`; Child definitions use `dontAsk`, first-party plugin-qualified Skills and their role-specific `mcp__research_sources__*` tools. User/project settings are disabled.
- The default runtime blocks before `query()`, CLI launch, Keychain lookup or HTTP. Its blocker list names the missing model, data-exfiltration gate, domains and source endpoints.
- The source gateway rejects disabled runtime, malformed/out-of-domain URL, missing endpoint, invalid financial query and excessive response. Mock-transport tests verify bounded search/financial evidence and that an opaque Keychain reference is resolved only at the approved HTTP boundary, without a real request.
- Product tests prove that a Public PDF can be registered, native parent `Agent` delegation IDs map to the three Child Runs, evidence-less Child output remains `未评估`, and the parent report is `partial` rather than a fabricated research conclusion.
- `sh harness/verify.sh` and a JUnit run pass: 181 passed, 11 skipped; JUnit `tests=192`, `failures=0`, `errors=0`, `skipped=11`.

## Deliberately not performed

No live Claude SDK query, provider/CLI authentication check, WebSearch/WebFetch, financial-data endpoint, PDF extraction, external source credential resolution or real model spend was attempted. The current default runtime status records the exact blockers in `offline-sdk-probe.json`.

## Required L3 authorization and probe

Before marking `engine_claude_research_native` available, the operator must supply an approved model identity and cost cap, exact public domains, search/financial source endpoints and (if applicable) opaque Keychain references, then upload an approved Public PDF. Run a controlled single-company probe and retain SDK/CLI/MCP versions, the three delegation IDs and timing, source evidence, cancellation outcome, cost/usage, data-exfiltration review and report citation audit. Failure of any item keeps TD-017/018/019/025/026 open.
