import asyncio
import json
from pathlib import Path

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from adapters.claude_research import (
    NativeResearchConfig, build_options, create_source_server, normalize_sdk_message,
    options_snapshot, runtime_status, stream_native_research, _deny_unexpected_tool,
)
from backend.analysis import Problem
from backend.app import create_app
from backend.research_sources import ResearchSourceGateway, SourcePolicy, policy_from_env


REQUEST = {
    'company': '测试公司', 'stock_code': 'SZ000001', 'objective': '生成带来源的研究草稿。',
    'report_resource_id': 'res_' + 'a' * 64, 'timeout_seconds': 60, 'max_cost_minor': 300,
}


class Gateway:
    async def search_news(self, query, limit):
        return {'query': query, 'results': [{'source_id': 'src_search'}]}

    async def fetch_url(self, url):
        return {'source_id': 'src_fetch', 'uri': url}

    async def financial_data(self, stock_code, metric_group):
        return {'source_id': 'src_financial', 'stock_code': stock_code}

    async def extract_pdf(self, resource_id, max_chars):
        return {'source_id': 'src_pdf', 'resource_id': resource_id}


def enabled_env(monkeypatch):
    values = {
        'HARNESS_CLAUDE_RESEARCH_RUNTIME': 'enabled',
        'HARNESS_CLAUDE_RESEARCH_EXTERNAL_DATA': 'enabled',
        'HARNESS_CLAUDE_RESEARCH_MODEL': 'claude-test-controlled',
        'HARNESS_CLAUDE_RESEARCH_ALLOWED_DOMAINS': 'finance.example,search.example',
        'HARNESS_CLAUDE_RESEARCH_SEARCH_ENDPOINT': 'https://search.example/v1/search',
        'HARNESS_CLAUDE_RESEARCH_FINANCIAL_ENDPOINT': 'https://finance.example/v1/financials',
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


def config():
    return NativeResearchConfig(model='claude-test-controlled', runtime_enabled=True, external_data_enabled=True,
                                allowed_domains=('finance.example', 'search.example'), cli_path='claude',
                                max_turns=12, max_cost_minor=300, timeout_seconds=60)


def test_native_sdk_configuration_is_fixed_to_agent_subagents_plugin_and_mcp():
    server = create_source_server(Gateway())
    options = build_options(config(), server)
    snapshot = options_snapshot(options)
    assert server['type'] == 'sdk' and server['name'] == 'research_sources'
    assert snapshot['tools'] == snapshot['allowed_tools'] == ['Agent']
    assert snapshot['setting_sources'] == snapshot['skills'] == []
    assert snapshot['permission_mode'] == 'dontAsk' and snapshot['strict_mcp_config']
    assert snapshot['plugin_paths'] == [str(Path(__file__).resolve().parents[1] / 'plugins/research-skills')]
    assert set(snapshot['agents']) == {'financial', 'industry', 'risk'}
    assert snapshot['agents']['financial']['skills'] == ['research-skills:financial-analysis']
    assert snapshot['agents']['financial']['tools'] == [
        'mcp__research_sources__financial_data', 'mcp__research_sources__pdf_extract', 'mcp__research_sources__web_fetch'
    ]
    assert all(agent['permissionMode'] == 'dontAsk' and agent['model'] == 'inherit' and agent['background']
               for agent in snapshot['agents'].values())
    assert type(asyncio.run(_deny_unexpected_tool('mcp__research_sources__web_search', {}, None))).__name__ == 'PermissionResultAllow'
    assert type(asyncio.run(_deny_unexpected_tool('Bash', {}, None))).__name__ == 'PermissionResultDeny'


def test_default_gate_is_truthful_and_native_request_has_no_product_side_effect(tmp_path):
    status = runtime_status({})
    assert not status['runtime_enabled'] and not status['external_data_enabled']
    assert {'runtime_gate_disabled', 'model_not_configured', 'search_source_not_configured'} <= set(status['blockers'])
    with TestClient(create_app(tmp_path / 'native.db', False), base_url='http://127.0.0.1') as client:
        response = client.post('/api/local/research-native', json=REQUEST, headers={'Idempotency-Key': 'native-gate'})
        assert response.status_code == 409
        assert response.json()['error']['code'] == 'CLAUDE_RESEARCH_RUNTIME_BLOCKED'
        assert not client.app.state.service.store.listing('tasks')
        runtime = client.get('/api/local/research-native/runtime').json()
        assert runtime['mode'] == 'claude_native_research@1' and not runtime['runtime_enabled']


def test_native_research_openapi_matches_the_static_contract(tmp_path):
    with TestClient(create_app(tmp_path / 'native-openapi.db', False), base_url='http://127.0.0.1') as client:
        runtime = client.get('/openapi.json').json()
    operation = runtime['paths']['/api/local/research-native']['post']
    assert operation['requestBody']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/native_research_request'
    }
    assert any(parameter['name'] == 'Idempotency-Key' and parameter['in'] == 'header'
               for parameter in operation['parameters'])
    assert runtime['components']['schemas']['native_research_request']['required'] == [
        'company', 'stock_code', 'objective', 'report_resource_id', 'timeout_seconds', 'max_cost_minor'
    ]
    static = yaml.safe_load((Path(__file__).resolve().parents[1] / 'specs/v1/openapi.yaml').read_text())
    static_operation = static['paths']['/local/research-native']['post']
    assert static_operation['requestBody']['content']['application/json']['schema']['$ref'].endswith(
        '#/$defs/native_research_request'
    )
    assert any(parameter.get('$ref') == '#/components/parameters/IdempotencyKey'
               for parameter in static_operation['parameters'])


def test_native_message_mapping_preserves_only_bounded_audit_fields():
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock
    delegated = AssistantMessage(content=[ToolUseBlock('tool_financial', 'Agent', {'subagent_type': 'financial', 'prompt': 'secret-like task content'})], model='claude-test')
    event = normalize_sdk_message(delegated)[0]
    assert event['kind'] == 'assistant.tool_use'
    assert event['payload']['subagent_type'] == 'financial'
    assert 'prompt' not in event['payload'] and len(event['payload']['input_sha256']) == 64
    text = normalize_sdk_message(AssistantMessage(content=[TextBlock('来源 src_abc')], model='claude-test', parent_tool_use_id='tool_financial'))[0]
    assert text['agent_scope'] == 'child' and text['parent_tool_use_id'] == 'tool_financial'
    result = normalize_sdk_message(ResultMessage(subtype='success', duration_ms=1, duration_api_ms=1, is_error=False, num_turns=2, session_id='s'))[0]
    assert result['kind'] == 'sdk.result' and result['payload']['num_turns'] == 2


def test_source_gateway_denies_before_network_and_enforces_domains():
    disabled = ResearchSourceGateway(SourcePolicy(False, ('search.example',), 'https://search.example/v1', 'https://search.example/v1'))
    with pytest.raises(Problem, match='外部资料工具默认关闭'):
        asyncio.run(disabled.search_news('啤酒', 3))
    active = ResearchSourceGateway(SourcePolicy(True, ('search.example',), 'https://search.example/v1', 'https://search.example/v1'))
    with pytest.raises(Problem, match='白名单'):
        asyncio.run(active.fetch_url('https://other.example/page'))
    with pytest.raises(Problem, match='endpoint'):
        policy_from_env({'HARNESS_CLAUDE_RESEARCH_EXTERNAL_DATA': 'enabled',
                         'HARNESS_CLAUDE_RESEARCH_ALLOWED_DOMAINS': 'search.example',
                         'HARNESS_CLAUDE_RESEARCH_SEARCH_ENDPOINT': 'https://other.example/search'})


def test_source_gateway_bounded_http_evidence_without_real_network():
    def handler(request):
        if request.url.host == 'search.example':
            return httpx.Response(200, json={'items': [{'title': '行业资料', 'url': 'https://search.example/news/1', 'snippet': '公开摘要'}]})
        if request.url.host == 'finance.example':
            return httpx.Response(200, json={'period': '2025', 'unit': 'CNY', 'revenue': 100})
        return httpx.Response(404)

    def client_factory():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='https://unused.example')

    gateway = ResearchSourceGateway(SourcePolicy(True, ('search.example', 'finance.example'), 'https://search.example/v1/search', 'https://finance.example/v1/data'), client_factory=client_factory)
    search = asyncio.run(gateway.search_news('啤酒', 1))
    financial = asyncio.run(gateway.financial_data('SZ000001', 'indicators'))
    assert search['results'][0]['source_id'] in gateway.evidence
    assert financial['source_id'] in gateway.evidence
    assert all(value['bytes'] <= 512 * 1024 and len(value['sha256']) == 64 for value in gateway.evidence.values())


def test_source_credential_is_resolved_only_when_the_approved_http_tool_runs():
    class Resolver:
        calls = []

        def resolve(self, ref):
            self.calls.append(ref)
            return 'test-secret'

    seen = []

    def handler(request):
        seen.append(request.headers.get('authorization'))
        return httpx.Response(200, json={'items': [{'title': '公开资料', 'url': 'https://search.example/item', 'snippet': '摘要'}]})

    resolver = Resolver()
    gateway = ResearchSourceGateway(
        SourcePolicy(True, ('search.example',), 'https://search.example/v1/search', 'https://search.example/v1/financials',
                     search_credential_ref='research-search'),
        credential_resolver=resolver,
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert resolver.calls == []
    asyncio.run(gateway.search_news('行业', 1))
    assert resolver.calls == ['research-search'] and seen == ['Bearer test-secret']


def test_stream_invokes_injected_query_only_after_enabled_gate(monkeypatch):
    enabled_env(monkeypatch)
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock
    calls = []

    async def fake_query(**kwargs):
        calls.append(kwargs)
        yield AssistantMessage(content=[ToolUseBlock('delegate_fin', 'Agent', {'subagent_type': 'financial'})], model='claude-test')
        yield AssistantMessage(content=[TextBlock('未评估')], model='claude-test', parent_tool_use_id='delegate_fin')
        yield ResultMessage(subtype='success', duration_ms=1, duration_api_ms=1, is_error=False, num_turns=2, session_id='session')

    events = asyncio.run(_collect(stream_native_research('做研究。', config(), Gateway(), query_fn=fake_query)))
    assert len(calls) == 1 and calls[0]['options'].agents['financial'].description
    assert [event['kind'] for event in events] == ['assistant.tool_use', 'assistant.text', 'sdk.result']


def test_product_run_maps_native_child_events_and_never_fakes_source_coverage(tmp_path, monkeypatch):
    enabled_env(monkeypatch)

    async def fake_native_stream(_prompt, _config, _gateway):
        for role in ('financial', 'industry', 'risk'):
            delegate = 'delegate_' + role
            yield {'kind': 'assistant.tool_use', 'agent_scope': 'parent', 'parent_tool_use_id': None,
                   'payload': {'tool_use_id': delegate, 'tool': 'Agent', 'input_sha256': 'a' * 64,
                               'input_bytes': 20, 'subagent_type': role}}
            yield {'kind': 'assistant.text', 'agent_scope': 'child', 'parent_tool_use_id': delegate,
                   'payload': {'text': '未评估：测试事件没有外部来源。', 'sha256': 'b' * 64, 'truncated': False}}
        yield {'kind': 'sdk.result', 'agent_scope': 'parent', 'parent_tool_use_id': None,
               'payload': {'subtype': 'success', 'is_error': False, 'num_turns': 4, 'duration_ms': 1,
                           'duration_api_ms': 1, 'total_cost_usd': 0.01, 'stop_reason': 'end_turn', 'usage': {}, 'errors': []}}

    monkeypatch.setattr('backend.research_native.stream_native_research', fake_native_stream)
    with TestClient(create_app(tmp_path / 'native-product.db', False), base_url='http://127.0.0.1') as client:
        upload = client.post('/api/local/research-native/documents?name=report.pdf', content=b'%PDF-1.4\nplaceholder',
                             headers={'content-type': 'application/pdf'})
        assert upload.status_code == 201, upload.text
        response = client.post('/api/local/research-native', headers={'Idempotency-Key': 'native-product'}, json={
            **REQUEST, 'report_resource_id': upload.json()['id'], 'max_cost_minor': 300,
        })
        assert response.status_code == 202, response.text
        root = response.json()['initial_run']['id']
        client.app.state.service.execute(root)
        detail = client.get('/api/local/research-native/' + root).json()
        assert detail['run']['status'] == 'succeeded'
        assert detail['run']['exit_reason'] == 'COMPLETED_WITH_WARNINGS'
        assert {child['role'] for child in detail['children']} == {'financial', 'industry', 'risk'}
        assert all(child['run']['status'] == 'succeeded' for child in detail['children'])
        manifest = next(item for item in detail['artifacts'] if item['name'] == 'native-research-manifest.json')
        result = client.get('/api/v1/artifacts/' + manifest['id'] + '/content').json()
        assert result['coverage'] == 'partial' and result['source_evidence'] == []
        assert result['background_execution_requested']
        assert {item['role'] for item in result['delegations']} == {'financial', 'industry', 'risk'}
        root_events = client.get('/api/v1/runs/' + root + '/events').json()['items']
        assert len([event for event in root_events if event['event_type'] == 'agent.delegated']) == 3


def test_native_child_cancel_escalates_to_the_full_sdk_run_tree(tmp_path, monkeypatch):
    enabled_env(monkeypatch)
    with TestClient(create_app(tmp_path / 'native-cancel.db', False), base_url='http://127.0.0.1') as client:
        upload = client.post('/api/local/research-native/documents?name=report.pdf', content=b'%PDF-1.4\nplaceholder',
                             headers={'content-type': 'application/pdf'})
        created = client.post('/api/local/research-native', headers={'Idempotency-Key': 'native-cancel'}, json={
            **REQUEST, 'report_resource_id': upload.json()['id'],
        }).json()
        root = created['initial_run']['id']
        detail = client.get('/api/local/research-native/' + root).json()
        child_id = detail['children'][0]['run']['id']
        cancelled = client.post('/api/v1/runs/' + child_id + ':cancel').json()
        assert cancelled['id'] == root and cancelled['status'] == 'cancelled'
        tree = client.get('/api/local/research-native/' + root).json()
        assert all(child['run']['status'] == 'cancelled' for child in tree['children'])
        events = client.get('/api/v1/runs/' + root + '/events').json()['items']
        assert any(event['event_type'] == 'research.native.cancel.requested' for event in events)


async def _collect(iterator):
    return [value async for value in iterator]
