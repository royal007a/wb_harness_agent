import asyncio
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

from backend.analysis import Problem
from backend.app import create_app
from backend.store import Store
from backend.support_chat import SupportChat
from backend.support_knowledge import DIM, LocalEmbedding, SupportKnowledge, normalize
from backend.support_providers import SupportProviders


class FixtureEmbedding:
    """Deterministic vectors test control logic, NOT semantic retrieval quality."""
    async def __call__(self, texts):
        return [[float(i == (0 if '退货' in t else 1)) for i in range(DIM)] for t in texts]


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_SUPPORT', 'enabled')
    master = tmp_path / 'master'
    master.write_bytes(os.urandom(32))
    master.chmod(0o600)
    monkeypatch.setenv('HARNESS_SUPPORT_MASTER_KEY_FILE', str(master))
    store = Store(tmp_path / 'knowledge.db')
    providers = SupportProviders(store)
    kb = SupportKnowledge(store, providers)
    kb.embed = FixtureEmbedding()
    yield kb
    store.close()


async def indexed(library, kid, text='## 退货\n七天内可以退货。', name='政策.txt'):
    doc = await library.upload(kid, {'name': name, 'text': text})
    task = library.jobs[doc['id']]
    await task
    return library.document(doc['id'])


def test_crud_ranking_scope_offsets_and_delete(library):
    one = library.save({'name': '售后'})
    two = library.save({'name': '私有测试'})
    async def scenario():
        a = await indexed(library, one['id'], '## 退货\r\n七天内可以退货。\r\n## 保修\r\n保修一年。')
        await indexed(library, two['id'], '退货期限99天。')
        assert a['document']['status'] == 'ready'
        source = library._row('support_documents', a['document']['id'])['source']
        for c in a['chunks']:
            assert source[c['start']:c['end']] == c['text']
            assert source[c['parent']['start']:c['parent']['end']] == c['parent']['text']
        results = await library.search([one['id']], '退货')
        assert len(results['items']) == 1
        item = results['items'][0]
        assert item['kb_id'] == one['id'] and item['score'] == 1
        assert '99' not in item['text']
        library.validate_sources(results['items'])
        library.delete(a['document']['id'], document=True)
        assert (await library.search([one['id']], '退货'))['items'] == []
        with pytest.raises(Problem): library.validate_sources(results['items'])
        assert len((await library.search([two['id']], '退货'))['items']) == 1
        library.delete(two['id'])
        assert library.store.db.execute('SELECT count(*) FROM support_chunks').fetchone()[0] == 0
    asyncio.run(scenario())


@pytest.mark.parametrize('fault', ['embedding', 'dimension', 'storage'])
def test_index_failure_leaves_no_partial_vectors(library, fault):
    k = library.save({'name': 'test'})
    if fault == 'embedding':
        async def broken(_): raise RuntimeError('SYNTH_SECRET')
        library.embed = broken
    if fault == 'dimension':
        async def short(texts): return [[1, 2] for _ in texts]
        library.embed = short
    if fault == 'storage':
        library.store.db.executescript("CREATE TRIGGER fail_second BEFORE INSERT ON support_chunks WHEN (SELECT count(*) FROM support_chunks)>0 BEGIN SELECT RAISE(ABORT,'SYNTH_SECRET'); END;")
    async def scenario():
        d = await indexed(library, k['id'], '## 退货\n退货七天。\n## 保修\n保修一年。')
        assert d['document']['status'] == 'failed'
        assert 'SYNTH_SECRET' not in json.dumps(d)
        assert library.store.db.execute('SELECT count(*) FROM support_chunks').fetchone()[0] == 0
    asyncio.run(scenario())


def test_busy_delete_disabled_and_cancel(library):
    k = library.save({'name': 'test'})
    async def scenario():
        entered = asyncio.Event()
        async def hang(_):
            entered.set()
            await asyncio.Future()
        library.embed = hang
        d = await library.upload(k['id'], {'name': 'a', 'text': '退货'})
        await entered.wait()
        with pytest.raises(Problem) as err: library.delete(k['id'])
        assert err.value.code == 'SUPPORT_DOCUMENT_BUSY'
        await library.close()
        assert library.document(d['id'])['document']['error_code'] == 'SUPPORT_INDEX_INTERRUPTED'
        library.save({'enabled': False}, k['id'])
        with pytest.raises(Problem): await library.search([k['id']], '退货')
        library.delete(k['id'])
    asyncio.run(scenario())


def test_recover_and_limits(library):
    k = library.save({'name': 'test'})
    library.store.db.execute('INSERT INTO support_documents VALUES(?,?,?,?)',
        ('csd_pending', k['id'], json.dumps({'id': 'csd_pending', 'status': 'processing'}), 'test'))
    library.store.db.commit()
    library.recover()
    assert library.document('csd_pending')['document']['error_code'] == 'SUPPORT_INDEX_RESTARTED'
    async def scenario():
        for bad in [{'name': 'n', 'text': ''}, {'name': 'n', 'text': 'x'*100001}, {'name': 'n', 'text': 'x', 'path': '/tmp/file'}]:
            with pytest.raises(Problem): await library.upload(k['id'], bad)
        d = await indexed(library, k['id'], '\n'.join('## 标题'+str(i)+'\n内容' for i in range(257)))
        assert d['document']['error_code'] == 'SUPPORT_CHUNK_LIMIT'
        for args in [{'query': ''}, {'query': 'x', 'top_k': True}, {'query': 'x', 'min_score': float('nan')}]:
            with pytest.raises(Problem): await library.search([k['id']], **args)
    asyncio.run(scenario())


@pytest.mark.parametrize('value', [[1], [0]*DIM, [float('nan')]*DIM, [True]*DIM])
def test_invalid_vector(value):
    with pytest.raises(Problem): normalize(value)


@pytest.mark.parametrize('mutation', ['none', 'delete', 'disable'])
def test_rag_chat_uses_sources_and_rechecks_before_publish(library, mutation):
    k = library.save({'name': '售后'})
    provider = library.providers.save({'name': 'p', 'api_key': 'synthetic', 'auto_probe': False})
    chat = SupportChat(library.store, library.providers)
    chat.knowledge = library
    agent = chat.agent_save({'name': 'a', 'provider_id': provider['id'], 'knowledge_ids': [k['id']]})
    session = chat.create_session({'agent_id': agent['id']})
    seen = []
    async def stream(providers, ident, payload):
        seen.append(payload)
        if mutation == 'delete': library.delete(k['id'])
        if mutation == 'disable': library.save({'enabled': False}, k['id'])
        yield {'delta': '七天内可以退货。'}
        yield {'result': {'message': {'role': 'assistant', 'content': '七天内可以退货。'},
                          'usage': {'input_tokens': 100, 'output_tokens': 10, 'total_tokens': 110}}}
    chat.stream_model = stream
    async def scenario():
        await indexed(library, k['id'])
        ex = chat.begin(session['id'], {'content': '退货'}, 'k')
        events = [e async for e in chat.stream(ex['id'])]
        assert '<knowledge>' in seen[0]['messages'][0]['content']
        assert '七天内' in seen[0]['messages'][0]['content']
        assert seen[0]['messages'][-1]['content'] == '退货'
        assert events[1]['type'] == 'sources'
        assert 'text' not in events[1]['items'][0]
        assert events[-1]['type'] == ('done' if mutation == 'none' else 'error')
        assert len(chat.detail(session['id'])['messages']) == (2 if mutation == 'none' else 1)
    asyncio.run(scenario())


def test_http_and_agent_binding(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_SUPPORT', 'enabled')
    with TestClient(create_app(tmp_path/'http.db', run_worker=False), base_url='http://localhost') as client:
        kb = client.post('/api/local/support/knowledge', json={'name': '客服'}).json()
        runtime = client.app.state.support_knowledge
        runtime.embed = FixtureEmbedding()
        response = client.post('/api/local/support/knowledge/'+kb['id']+'/documents', json={'name': '手册', 'text': '退货7天。'*1000})
        assert response.status_code == 202
        doc_id = response.json()['id']
        for _ in range(50):
            detail = client.get('/api/local/support/documents/'+doc_id).json()
            if detail['document']['status'] != 'processing': break
        assert detail['document']['status'] == 'ready'
        assert client.post('/api/local/support/knowledge/'+kb['id']+'/search', json={'query': '退货'}).status_code == 200
        assert client.put('/api/local/support/knowledge/'+kb['id'], json={'enabled': False}).status_code == 200
        assert client.post('/api/local/support/knowledge/'+kb['id']+'/search', json={'query': '退货'}).status_code == 409
        assert 'support-knowledge.js' in client.get('/support').text


def test_embedding_cancel_terminates_worker(tmp_path, monkeypatch):
    (tmp_path/'support-model.json').write_text('{}')
    monkeypatch.setenv('HARNESS_SUPPORT_EMBEDDING_DIR', str(tmp_path))
    original = asyncio.create_subprocess_exec
    spawned = []
    async def fake(*args, **kwargs):
        assert 'NODE_OPTIONS' not in kwargs['env'] and kwargs['env']['HF_HUB_OFFLINE'] == '1'
        process = await original(sys.executable, '-c', 'import time; time.sleep(60)', **kwargs)
        spawned.append(process)
        return process
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', fake)
    async def scenario():
        job = asyncio.create_task(LocalEmbedding()(['synthetic text']))
        while not spawned: await asyncio.sleep(.01)
        job.cancel()
        with pytest.raises(asyncio.CancelledError): await job
        assert spawned[0].returncode is not None
    asyncio.run(scenario())


@pytest.mark.skipif(not os.environ.get('HARNESS_SUPPORT_EMBEDDING_DIR'), reason='Explicit local BGE model required')
def test_real_bge_semantic_query(library):
    library.embed = LocalEmbedding()
    k = library.save({'name': '真实本地向量测试'})
    async def scenario():
        await indexed(library, k['id'], '## 退换货政策\n自签收日起七天内，未拆封商品支持无理由退货。\n## 保修期限\n电子产品享受一年免费保修。\n## 会员权益\n金卡会员享受九折优惠。')
        result = await library.search([k['id']], '买的东西不想要了，可以退回去吗？', min_score=0)
        assert result['items'] and '退货' in result['items'][0]['text']
        assert result['dimension'] == 512
    asyncio.run(scenario())
