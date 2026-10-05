"""Read-only research probes of baseline 1a4d4ce, not desired-behavior regressions.

Official DSH SDK subprocess + synthetic Provider + temporary SQLite only.
These assertions intentionally describe current limitations. Do not add to verify.sh.
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.dsh_provider import parse_response


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_DSH_LOCAL', 'enabled')
    monkeypatch.setenv('HARNESS_DSH_RUN_ROOT', str(tmp_path / 'owned'))
    monkeypatch.delenv('HARNESS_DSH_REAL_ENABLED', raising=False)
    monkeypatch.delenv('HARNESS_DSH_CREDENTIAL_REF', raising=False)
    from backend.agent_runtime import KeyringCredentialResolver
    monkeypatch.setattr(KeyringCredentialResolver, 'resolve',
                        lambda *a: pytest.fail('no credentials in research probes'))
    with TestClient(create_app(tmp_path / 'probe.db', run_worker=False),
                    base_url='http://localhost') as value:
        yield value


def submit(client, document):
    result = client.post('/api/local/dsh/runs', headers={'Idempotency-Key': 'research'},
        json={'objective': '核对付款条件及例外，引用证据。', 'document': document,
              'mode': 'integration_probe', 'public_data_confirmed': True})
    assert result.status_code == 201, result.text
    return result.json()['initial_run']['id']


def reply(text='', tool=None, args=None):
    message = {'content': text}
    if tool:
        message['tool_calls'] = [{'id': 'research_call', 'type': 'function', 'function': {
            'name': tool, 'arguments': json.dumps(args)}}]
    return parse_response({'choices': [{'finish_reason': 'tool_calls' if tool else 'stop',
                                       'message': message}],
                           'usage': {'prompt_tokens': 10, 'completion_tokens': 10,
                                     'total_tokens': 20}})


def test_citation_relation_does_not_validate_the_claim(client):
    ident = submit(client, '第1条 付款\n验收后30天付款。')
    rt = client.app.state.service.dsh
    calls = []
    async def provider(payload, limit):
        calls.append(payload)
        if len(calls) == 1:
            return reply(tool='read_clause', args={'clause_id': 'clause-1'})
        tool_messages = [m for m in payload['messages'] if m['role'] == 'tool']
        assert '30天' in tool_messages[-1]['content']
        return reply('依据 clause-1，付款期限为验收后300天。')
    rt.send_probe = provider
    rt.execute(ident)
    detail = rt.detail(ident)
    assert detail['run']['status'] == 'succeeded', detail
    artifact = rt.store.db.execute('SELECT body FROM artifacts WHERE id=?',
                                  (detail['artifacts'][0]['id'],)).fetchone()[0]
    assert '300天' in artifact.decode()
    assert any(e['event_type'] == 'run.succeeded' and e['data']['human_review_required']
               for e in rt.store.events(ident))
    print('OBSERVATION citation-valid false claim published as human-review-required draft; model_calls=2')


def test_repeated_same_read_stops_at_hard_cap_not_progress(client):
    ident = submit(client, '第1条 付款\n验收后30天付款。')
    rt = client.app.state.service.dsh
    calls = []
    async def provider(payload, limit):
        calls.append(payload)
        return reply(tool='read_clause', args={'clause_id': 'clause-1'})
    rt.send_probe = provider
    rt.execute(ident)
    detail = rt.detail(ident)
    tools = [e for e in rt.store.events(ident) if e['event_type'] == 'dsh.tool.completed']
    assert detail['run']['exit_reason'] == 'DSH_MODEL_CALL_LIMIT', detail
    assert len(calls) == len(tools) == 8
    assert not detail['artifacts']
    print('OBSERVATION repeated identical read: model_calls=8 tool_calls=8; hard cap, no early progress stop')


def test_first_three_matches_can_omit_a_later_exception(client):
    document = ('第1条 付款\n付款需验收。\n第2条 付款\n付款需发票。\n'
                '第3条 付款\n付款使用转账。\n第4条 付款例外\n有质量争议时暂停付款。')
    ident = submit(client, document)
    rt = client.app.state.service.dsh
    retrieved = []
    async def provider(payload, limit):
        messages = [m for m in payload['messages'] if m['role'] == 'tool']
        if not messages:
            return reply(tool='search_document', args={'query': '付款'})
        retrieved.extend(json.loads(messages[-1]['content']))
        assert len(retrieved) == 3
        assert not any('质量争议' in item['text'] for item in retrieved)
        return reply('付款需验收；依据 clause-1。')
    rt.send_probe = provider
    rt.execute(ident)
    detail = rt.detail(ident)
    assert detail['run']['status'] == 'succeeded', detail
    assert [item['clause_id'] for item in retrieved] == ['clause-1', 'clause-2', 'clause-3']
    print('OBSERVATION search first 3 omits clause-4 exception; succeeds as draft, not coverage proof')
