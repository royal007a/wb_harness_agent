import asyncio
import copy
import json

import pytest

from backend.analysis import Problem
from backend.support_chat import SupportChat
from backend.support_workflows import SupportWorkflows, definition, render
from test_support_knowledge import library, indexed


def node(key, kind, **config): return {'id': key, 'type': kind, 'config': config}
def edge(source, target, condition=None): return {'source': source, 'target': target, 'condition': condition}


def linear():
    return {'name': '客服流', 'description': '', 'enabled': True,
        'nodes': [node('start', 'START'), node('answer', 'LLM', prompt='回复：{{start.input}}'), node('end', 'END', text='{{answer.output}}')],
        'edges': [edge('start', 'answer'), edge('answer', 'end')]}


def branch():
    return {'name': '分支', 'description': '', 'enabled': True,
        'nodes': [node('start', 'START'), node('route', 'CONDITION', left='{{start.input}}', operator='contains', right='退款'),
                  node('refund', 'END', text='退款请先提供订单号。'), node('other', 'END', text='请描述问题。')],
        'edges': [edge('start', 'route'), edge('route', 'refund', True), edge('route', 'other', False)]}


@pytest.fixture
def runtime(library):
    workflows = SupportWorkflows(library.store, library.providers)
    chat = SupportChat(library.store, library.providers)
    chat.knowledge, chat.workflows = library, workflows
    provider = library.providers.save({'name': 'p', 'api_key': 'synthetic', 'auto_probe': False})
    chat.provider_id, chat.sent = provider['id'], []
    async def stream(providers, ident, payload):
        chat.sent.append(copy.deepcopy(payload))
        yield {'delta': '分类中间值不应直接展示'}
        yield {'result': {'message': {'role': 'assistant', 'content': '合成客服回答'},
                          'usage': {'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120}}}
    chat.stream_model = stream
    return chat


def prepare(runtime, flow=None, **kwargs):
    wf = runtime.workflows.save(flow or linear())
    agent = runtime.agent_save({'name': 'a', 'provider_id': runtime.provider_id, 'workflow_ids': [wf['id']], **kwargs})
    session = runtime.create_session({'agent_id': agent['id']})
    return wf, session


async def collect(runtime, ex): return [e async for e in runtime.stream(ex['id'])]


def test_crud_linear_final_publication_replay(runtime):
    wf, session = prepare(runtime)
    assert runtime.workflows.get(wf['id'])['nodes'] == linear()['nodes']
    ex = runtime.begin(session['id'], {'content': '你好'}, 'key')
    result = asyncio.run(collect(runtime, ex))
    assert result[-1]['type'] == 'done'
    assert [e['content'] for e in result if e['type'] == 'delta'] == ['合成客服回答']
    assert result[-1]['budget']['spent'] == 120
    runs = runtime.workflows.runs(wf['id'])
    assert runs[0]['status'] == 'succeeded'
    assert [n['node'] for n in runs[0]['steps']] == ['start', 'answer', 'end']
    assert all(n['status'] == 'succeeded' for n in runs[0]['steps'])
    assert '合成客服回答' not in json.dumps(runs, ensure_ascii=False)
    assert asyncio.run(collect(runtime, ex))[0]['replayed']
    assert len(runtime.sent) == 1
    runtime.workflows.delete(wf['id'])
    assert len(runtime.workflows.runs(wf['id'])) == 1


@pytest.mark.parametrize('question,expected,path', [('想退款', '退款请先提供订单号。', 'refund'), ('你好', '请描述问题。', 'other')])
def test_branch_does_not_call_unselected_nodes(runtime, question, expected, path):
    wf, s = prepare(runtime, branch())
    ex = runtime.begin(s['id'], {'content': question}, 'k')
    result = asyncio.run(collect(runtime, ex))
    assert result[-1]['message']['content'] == expected
    assert runtime.sent == []
    assert runtime.workflows.runs(wf['id'])[0]['steps'][-1]['node'] == path


@pytest.mark.parametrize('bad', ['cycle', 'missing', 'branch', 'unknown', 'duplicate', 'unreachable', 'bad_type', 'extra', 'expression'])
def test_invalid_definition_zero_write(runtime, bad):
    body = branch()
    if bad == 'cycle': body['edges'][1]['target'] = 'start'
    if bad == 'missing': body['edges'][0]['target'] = 'no_such'
    if bad == 'branch': body['edges'][2]['condition'] = True
    if bad == 'unknown': body['nodes'][1]['type'] = 'PYTHON'
    if bad == 'duplicate': body['nodes'].append(body['nodes'][0])
    if bad == 'unreachable': body['nodes'].append(node('unused', 'END', text='x'))
    if bad == 'bad_type': body['edges'][0]['condition'] = 0
    if bad == 'extra': body['nodes'][0]['config']['extra'] = 1
    if bad == 'expression': body['nodes'][1]['config']['operator'] = 'eval'
    changes = runtime.store.db.total_changes
    with pytest.raises(Problem): runtime.workflows.save(body)
    assert runtime.store.db.total_changes == changes


def test_render_is_single_pass_and_missing_is_error():
    assert render('{{start.input}}', {'start.input': '{{answer.output}}', 'answer.output': 'NO'}) == '{{answer.output}}'
    with pytest.raises(Problem): render('{{unknown.output}}', {})
    assert render('literal __import__("os")', {}) == 'literal __import__("os")'


@pytest.mark.parametrize('mutation', ['missing_variable', 'provider_error', 'config_changed', 'publication_error'])
def test_failure_never_commits_assistant(runtime, mutation):
    flow = linear()
    if mutation == 'missing_variable': flow['nodes'][-1]['config']['text'] = '{{missing.output}}'
    wf, s = prepare(runtime, flow)
    original = runtime.stream_model
    if mutation in {'provider_error', 'config_changed'}:
        async def changed(*args):
            if mutation == 'provider_error': raise RuntimeError('SYNTH_SECRET')
            runtime.workflows.save({'description': 'changed'}, wf['id'])
            async for event in original(*args): yield event
        runtime.stream_model = changed
    if mutation == 'publication_error':
        runtime.store.db.executescript("CREATE TRIGGER reject_assistant BEFORE INSERT ON support_messages WHEN json_extract(NEW.doc,'$.role')='assistant' BEGIN SELECT RAISE(ABORT,'SYNTH_SECRET'); END;")
    ex = runtime.begin(s['id'], {'content': '你好'}, 'key')
    result = asyncio.run(collect(runtime, ex))
    assert result[-1]['type'] == 'error'
    assert len(runtime.detail(s['id'])['messages']) == 1
    runs = runtime.workflows.runs(wf['id'])
    assert runs[0]['status'] == 'failed'
    assert 'SYNTH_SECRET' not in json.dumps(result)


def test_shared_budget_blocks_second_llm(runtime):
    flow = linear()
    flow['nodes'].insert(2, node('second', 'LLM', prompt='再答{{answer.output}}'))
    flow['nodes'][-1]['config']['text'] = '{{second.output}}'
    flow['edges'] = [edge('start', 'answer'), edge('answer', 'second'), edge('second', 'end')]
    wf, s = prepare(runtime, flow, token_budget=1024060, max_output_tokens=32)
    ex = runtime.begin(s['id'], {'content': '你好'}, 'k')
    events = asyncio.run(collect(runtime, ex))
    assert events[-1]['error_code'] == 'BUSINESS_TOKEN_BUDGET_EXHAUSTED'
    assert len(runtime.sent) == 1
    snapshot = runtime.ledger.snapshot(ex['id'])
    assert snapshot['spent'] == 120 and snapshot['reserved'] == 0
    assert runtime.workflows.runs(wf['id'])[0]['status'] == 'failed'


def test_cancel_waiting_llm_closes_stream_and_marks_node(runtime):
    wf, s = prepare(runtime)
    async def scenario():
        entered, closed = asyncio.Event(), asyncio.Event()
        async def wait(*args):
            entered.set()
            try:
                await asyncio.Future()
                yield {}
            finally: closed.set()
        runtime.stream_model = wait
        ex = runtime.begin(s['id'], {'content': '你好'}, 'k')
        task = asyncio.create_task(collect(runtime, ex))
        await entered.wait()
        runtime.cancel(ex['id'])
        events = await asyncio.wait_for(task, 3)
        assert closed.is_set() and events[-1]['type'] == 'error'
        run = runtime.workflows.runs(wf['id'])[0]
        assert run['status'] == 'cancelled' and run['steps'][-1]['status'] == 'cancelled'
    asyncio.run(scenario())


def test_knowledge_node_is_bound_and_sources_persist(runtime):
    library = runtime.knowledge
    kb = library.save({'name': '售后'})
    flow = linear()
    flow['nodes'].insert(1, node('kb', 'KNOWLEDGE', kb_id=kb['id'], query='{{start.input}}', top_k=3))
    flow['nodes'][2]['config']['prompt'] = '根据资料回答：{{kb.output}}\n问题：{{start.input}}'
    flow['edges'] = [edge('start', 'kb'), edge('kb', 'answer'), edge('answer', 'end')]
    wf, s = prepare(runtime, flow, knowledge_ids=[kb['id']])
    async def scenario():
        await indexed(library, kb['id'])
        ex = runtime.begin(s['id'], {'content': '退货'}, 'k')
        result = await collect(runtime, ex)
        assert result[-1]['type'] == 'done'
        assert '七天' in runtime.sent[0]['messages'][1]['content']
        assert runtime.get('exchanges', ex['id'])['sources'][0]['kb_id'] == kb['id']
    asyncio.run(scenario())
    _, denied = prepare(runtime, flow)
    ex = runtime.begin(denied['id'], {'content': '退货'}, 'k')
    assert asyncio.run(collect(runtime, ex))[-1]['error_code'] == 'SUPPORT_KNOWLEDGE_DENIED'


def test_tool_node_enforces_agent_permissions(runtime):
    async def lookup(args, agent, ctx): return {'order': args['id'], 'status': '已签收'}
    runtime.tools.register('lookup', 'order lookup', {'type': 'object', 'required': ['id'],
        'properties': {'id': {'type': 'string'}}, 'additionalProperties': False}, lookup)
    flow = {'name': '订单查询', 'description': '', 'enabled': True,
        'nodes': [node('start', 'START'), node('order', 'TOOL', name='lookup', arguments={'id': '{{start.input}}'}),
                  node('end', 'END', text='查询结果：{{order.output}}')], 'edges': [edge('start', 'order'), edge('order', 'end')]}
    wf, s = prepare(runtime, flow, tools=['lookup'])
    ex = runtime.begin(s['id'], {'content': '123'}, 'k')
    assert '已签收' in asyncio.run(collect(runtime, ex))[-1]['message']['content']
    _, denied = prepare(runtime, flow)
    ex = runtime.begin(denied['id'], {'content': '123'}, 'k')
    assert asyncio.run(collect(runtime, ex))[-1]['error_code'] == 'SUPPORT_TOOL_DENIED'


def test_freeze_revision_and_recover(runtime):
    wf, s = prepare(runtime)
    runtime.workflows.save({'description': 'new'}, wf['id'])
    ex = runtime.begin(s['id'], {'content': '你好'}, 'k')
    assert asyncio.run(collect(runtime, ex))[-1]['error_code'] == 'SUPPORT_WORKFLOW_CHANGED'
    assert runtime.sent == []
    runtime.store.db.execute('INSERT INTO support_workflow_runs VALUES(?,?,?)', ('cse_old', wf['id'], json.dumps({'id': 'cse_old', 'status': 'running'})))
    runtime.store.db.execute('INSERT INTO support_workflow_steps VALUES(?,?,?)', ('step_old', 'cse_old', json.dumps({'status': 'running'})))
    runtime.store.db.commit()
    runtime.workflows.recover()
    run = runtime.workflows.runs(wf['id'])[0]
    assert run['status'] == 'failed' and run['steps'][0]['error_code'] == 'SUPPORT_RESTARTED'
