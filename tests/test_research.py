import copy
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.analysis import Problem
from backend.service import validate
from backend.store import dumps

BODY = {'companies':['demo_a'], 'roles':['financial','industry','risk'], 'concurrency':3,
        'failure_policy':'continue_with_warning', 'scenario':'complete', 'timeout_seconds':60, 'max_steps':4}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path/'research.db',False),base_url='http://127.0.0.1') as c:
        yield c


def submit(client, **changes):
    response=client.post('/api/local/research',json={**BODY,**changes},headers={'Idempotency-Key':str(time.monotonic_ns())})
    assert response.status_code==202,response.text
    return response.json()['initial_run']['id']


def test_success_contracts_sources_and_trace(client):
    root=submit(client,companies=['demo_a','demo_b','demo_c'],max_steps=10)
    service=client.app.state.service
    service.execute(root)
    detail=client.get('/api/local/research/'+root).json()
    assert detail['run']['status']=='succeeded' and len(detail['children'])==9
    validate('task',detail['task'])
    root_trace=service.store.events(root)[0]['trace_id']
    sources=set()
    for child in detail['children']:
        run=child['run']; validate('run',run)
        assert run['parent_run_id']==root and run['status']=='succeeded'
        assert run['effective_permissions']['allowed_tools']==['resource.inspect']
        sources.add(child['assignment']['resource_id'])
        for event in service.store.events(run['id']):
            validate('event',event); assert event['trace_id']==root_trace
            assert event['step_id'] != run['parent_step_id']
        assert any(e['event_type']=='tool.call.completed' for e in service.store.events(run['id']))
        result=client.get('/api/v1/artifacts/'+child['artifacts'][0]['id']+'/content').json()
        assert result['synthetic'] and result['company']==child['assignment']['company']
        assert result['evidence'][0]['resource_id']==child['assignment']['resource_id']
        if result['role']=='financial':
            assert result['metrics']=={'profit_margin':'0.1','liabilities_to_assets':'0.3'}
    assert len(sources)==9
    artifact=next(a for a in detail['artifacts'] if a['name']=='research-manifest.json')
    manifest=client.get('/api/v1/artifacts/'+artifact['id']+'/content').json()
    assert manifest['successful']==9 and manifest['coverage']=='complete'
    assert manifest['risk_assessment']=='not_assessed' and not manifest['real_model']
    assert manifest['usage']['steps_used']==10


@pytest.mark.parametrize('changes', [{'concurrency':4},{'companies':['demo_a','demo_a']},{'roles':['Bash']},
                                   {'model':'anything'},{'max_steps':3},{'timeout_seconds':0}])
def test_reject_before_writes(client,changes):
    response=client.post('/api/local/research',json={**BODY,**changes},headers={'Idempotency-Key':'invalid'})
    assert response.status_code==422
    assert not client.app.state.service.store.listing('tasks')
    assert not client.app.state.service.store.listing('resources')


def test_concurrent_idempotency_and_rerun(client):
    research=client.app.state.service.research
    with ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(lambda _:research.create(copy.deepcopy(BODY),'same'),range(5)))
    assert len({r['initial_run']['id'] for r in results})==1
    root=results[0]['initial_run']['id']; task=results[0]['task']['id']
    assert len(research.children(root))==3
    assert client.post('/api/local/research',json={**BODY,'concurrency':1},headers={'Idempotency-Key':'same'}).status_code==409
    before=research.detail(root)['task']
    child=research.children(root)[0]['id']
    assert client.post('/api/v1/tasks/'+task+'/runs',json={'based_on_run_id':child},headers={'Idempotency-Key':'bad-rerun'}).status_code==422
    response=client.post('/api/v1/tasks/'+task+'/runs',json={'based_on_run_id':root},headers={'Idempotency-Key':'rerun'})
    assert response.status_code==202,response.text
    new=response.json()
    assert new['id']!=root and new['attempt_number']==2 and len(research.children(new['id']))==3
    assert research.detail(root)['task']==before


@pytest.mark.parametrize('policy,status', [('continue_with_warning','succeeded'),('fail_parent','failed')])
def test_partial_failure(client,policy,status):
    root=submit(client,scenario='missing_risk',failure_policy=policy)
    client.app.state.service.execute(root)
    detail=client.get('/api/local/research/'+root).json()
    assert detail['run']['status']==status
    if status=='succeeded':
        assert detail['run']['exit_reason']=='COMPLETED_WITH_WARNINGS'
        manifest=client.get('/api/v1/artifacts/'+detail['artifacts'][0]['id']+'/content').json()
        assert manifest['coverage']=='partial' and manifest['failed']==1
        assert '未评估' in client.get('/api/v1/artifacts/'+detail['artifacts'][1]['id']+'/content').text
    else:
        assert not detail['artifacts']
    assert all(c['run']['status'] in {'succeeded','failed','cancelled'} for c in detail['children'])


def test_all_failed_not_success(client):
    root=submit(client,roles=['risk'],scenario='missing_risk')
    client.app.state.service.execute(root)
    assert client.get('/api/local/research/'+root).json()['run']['status']=='failed'


def test_parallel_overlap_context_and_global_limit(client,monkeypatch):
    service=client.app.state.service; research=service.research
    roots=[submit(client),submit(client,companies=['demo_b'])]
    original=research.executor.run
    lock=threading.Lock(); release=threading.Event(); reached=threading.Event()
    active=0; peak=0; seen=[]
    def slow(context,check):
        nonlocal active,peak
        assert set(context)=={'company','role','resource_id','input_bytes','allowed_tools','limits'}
        with lock:
            active+=1; peak=max(peak,active); seen.append(context['resource_id'])
            if active==3: reached.set()
        try:
            while not release.wait(.01): check()
            return original(context,check)
        finally:
            with lock: active-=1
    monkeypatch.setattr(research.executor,'run',slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(service.execute,r) for r in roots]
        assert reached.wait(3), 'No actual overlap'
        release.set()
        for f in futures: f.result(timeout=5)
    assert peak==3 and len(seen)==6 and len(set(seen))==6
    assert all(research.detail(r)['run']['status']=='succeeded' for r in roots)


def test_running_parent_cancel_no_late_publication(client,monkeypatch):
    service=client.app.state.service; root=submit(client)
    entered=threading.Event()
    def slow(context,check):
        entered.set()
        while True:
            check(); time.sleep(.01)
    monkeypatch.setattr(service.research.executor,'run',slow)
    thread=threading.Thread(target=service.execute,args=(root,));thread.start()
    assert entered.wait(2)
    start=time.monotonic()
    assert client.post('/api/v1/runs/'+root+':cancel').json()['status']=='cancelled'
    thread.join(2)
    assert not thread.is_alive() and time.monotonic()-start<2
    detail=service.research.detail(root)
    assert all(c['run']['status']=='cancelled' and not c['artifacts'] for c in detail['children'])
    assert not detail['artifacts']


def test_queued_child_cancel_is_explicit_partial(client):
    service=client.app.state.service;root=submit(client)
    child=service.research.children(root)[0]['id']
    client.post('/api/v1/runs/'+child+':cancel')
    service.execute(root)
    assert service.research.detail(root)['run']['exit_reason']=='COMPLETED_WITH_WARNINGS'


@pytest.mark.parametrize('fault', ['result','permissions','budget','version'])
def test_untrusted_boundary_rejected(client,monkeypatch,fault):
    service=client.app.state.service;root=submit(client,roles=['financial'])
    child=service.research.children(root)[0]
    if fault=='result':
        def wrong(context,check):
            return {'summary':'ignore rules', 'evidence':[{'resource_id':'res_other'}]}
        monkeypatch.setattr(service.research.executor,'run',wrong)
    elif fault=='version':
        monkeypatch.setattr(service.research.executor,'version','changed')
    else:
        if fault=='permissions': child['effective_permissions']['allowed_tools'].append('shell.exec')
        else: child['effective_limits']['max_turns']=100
        with service.store.transaction() as db:
            db.execute('UPDATE runs SET doc=? WHERE id=?',(dumps(child),child['id']))
    service.execute(root)
    assert service.research.detail(root)['run']['status']=='failed'
    assert not service.store.artifact_list(child['id'])


def test_timeout_before_start_and_double_execution(client):
    service=client.app.state.service;root=submit(client)
    with service.store.transaction() as db:
        run=service.store.get('runs',root)
        run['created_at']=(datetime.now(timezone.utc)-timedelta(seconds=200)).isoformat()
        db.execute('UPDATE runs SET doc=? WHERE id=?',(dumps(run),root))
    service.execute(root)
    assert service.store.get('runs',root)['status']=='expired'
    assert all(c['status']=='cancelled' for c in service.research.children(root))
    other=submit(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(service.execute,[other,other]))
    assert len(service.store.artifact_list(other))==2


def test_restart_closes_orphan_children(tmp_path):
    dbpath=tmp_path/'restart.db'
    with TestClient(create_app(dbpath,False),base_url='http://127.0.0.1') as client:
        root=submit(client)
        service=client.app.state.service
        with service.store.transaction() as db:
            run=service.store.get('runs',root);run['status']='running'
            service.store.event(db,run,'run.started')
        children=[c['id'] for c in service.research.children(root)]
    with TestClient(create_app(dbpath,True),base_url='http://127.0.0.1') as client:
        detail=client.get('/api/local/research/'+root).json()
        assert detail['run']['exit_reason']=='SERVER_RESTARTED'
        assert all(c['run']['status']=='cancelled' for c in detail['children'])
        assert {c['run']['id'] for c in detail['children']}==set(children)


@pytest.mark.parametrize('concurrency',[1,2,3])
def test_per_tree_concurrency(client,monkeypatch,concurrency):
    service=client.app.state.service;root=submit(client,concurrency=concurrency)
    original=service.research.executor.run
    release=threading.Event();reached=threading.Event();lock=threading.Lock()
    active=0;peak=0
    def slow(context,check):
        nonlocal active,peak
        with lock:
            active+=1;peak=max(peak,active)
            if active==concurrency: reached.set()
        try:
            while not release.wait(.01): check()
            return original(context,check)
        finally:
            with lock: active-=1
    monkeypatch.setattr(service.research.executor,'run',slow)
    thread=threading.Thread(target=service.execute,args=(root,));thread.start()
    try:
        assert reached.wait(3)
    finally:
        release.set();thread.join(3)
    assert not thread.is_alive() and peak==concurrency
    assert service.research.detail(root)['run']['status']=='succeeded'


def test_atomic_queue_capacity(client):
    service=client.app.state.service
    for _ in range(3): submit(client,companies=['demo_a','demo_b','demo_c'],max_steps=10)
    before={name:len(service.store.listing(name)) for name in ('tasks','runs','resources')}
    response=client.post('/api/local/research',json={**BODY,'scenario':'missing_risk'},headers={'Idempotency-Key':'overflow'})
    assert response.status_code==429
    assert {name:len(service.store.listing(name)) for name in before}==before


def test_reserved_total_budget_checked_before_dispatch(client):
    root=submit(client);service=client.app.state.service
    with service.store.transaction() as db:
        run=service.store.get('runs',root);run['effective_limits']['max_turns']=3
        db.execute('UPDATE runs SET doc=? WHERE id=?',(dumps(run),root))
    service.execute(root)
    assert service.store.get('runs',root)['exit_reason']=='BUDGET_EXCEEDED'
    assert all(c['status']=='cancelled' for c in service.research.children(root))


def test_single_analysis_rejects_non_csv_and_listing_uses_root(client):
    from backend.service import local_task
    root=submit(client);service=client.app.state.service
    task=service.research.detail(root)['task']
    response=client.post('/api/v1/tasks',json=local_task(task['context']['resource_ids'][0],'must reject'),
                         headers={'Idempotency-Key':'not-csv'})
    assert response.status_code==422
    assert client.get('/api/v1/tasks').json()['items'][0]['latest_run']['id']==root


def test_persisted_queued_tree_starts_after_restart(tmp_path):
    target=tmp_path/'queued.db'
    with TestClient(create_app(target,False),base_url='http://127.0.0.1') as client:
        root=submit(client)
    with TestClient(create_app(target,True),base_url='http://127.0.0.1') as client:
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            result=client.get('/api/local/research/'+root).json()
            if result['run']['status']=='succeeded':break
            time.sleep(.03)
        assert result['run']['status']=='succeeded'
        assert len(result['children'])==3
