"""Regenerate HA-0027's redacted, offline SDK construction evidence.

This intentionally does not call `query()`, the Claude CLI, a credential
backend or HTTP.  It only constructs SDK Python objects and serializes their
safe configuration snapshot so reviewers can distinguish this L2 evidence
from the required, separately approved L3 live probe.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.claude_research import (
    NativeResearchConfig,
    build_options,
    create_source_server,
    options_snapshot,
    runtime_status,
)


OUTPUT = ROOT / 'harness/evidence/HA-0027/offline-sdk-probe.json'


class OfflineGateway:
    """Never used by this probe; it makes MCP construction type-correct."""

    async def search_news(self, _query, _limit):
        raise AssertionError('offline evidence must not invoke a source tool')

    async def fetch_url(self, _url):
        raise AssertionError('offline evidence must not invoke a source tool')

    async def financial_data(self, _stock_code, _metric_group):
        raise AssertionError('offline evidence must not invoke a source tool')

    async def extract_pdf(self, _resource_id, _max_chars):
        raise AssertionError('offline evidence must not invoke a source tool')


def main() -> None:
    status = runtime_status({})
    config = NativeResearchConfig(
        model='claude-test-controlled', runtime_enabled=True, external_data_enabled=True,
        allowed_domains=('finance.example', 'search.example'), cli_path=status['cli_path'],
        max_turns=12, max_cost_minor=300, timeout_seconds=60,
    )
    server = create_source_server(OfflineGateway())
    options = build_options(config, server)
    evidence = {
        'default_runtime_status': status,
        'mcp_server': {'type': server['type'], 'name': server['name']},
        'options': options_snapshot(options),
        'not_performed': ['query', 'claude_cli', 'keychain', 'http'],
    }
    OUTPUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    print(OUTPUT)


if __name__ == '__main__':
    main()
