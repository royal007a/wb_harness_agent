"""Bounded synthetic DSH release smoke; no external Provider credentials or calls."""
import argparse
import hashlib
import json
import time
from pathlib import Path
import httpx

DOCUMENT = '公开合成部署验收合同\n第一条 付款\n甲方验收后30日内付款。发生质量争议时，甲方可暂停付款。\n第二条 争议解决\n双方协商解决。'

def verify(client, release, run_id=None):
    def get(path):
        r=client.get(path);r.raise_for_status();return r.json()
    status=get('/api/local/dsh/runtime')
    assert status['release']==release and status['installed'],status
    assert not status['shell_enabled'] and not status['network_tools_enabled']
    previous={r['id'] for r in get('/api/local/dsh/runs')['items']}
    created=run_id is None
    if created:
        import uuid
        payload=dict(objective='核对付款期限和例外，引用条款。',document=DOCUMENT,mode='integration_probe',
                     public_data_confirmed=True,template='payment_terms',token_limit=200000,timeout_seconds=120)
        response=client.post('/api/local/dsh/runs',json=payload,headers={'Idempotency-Key':'release-'+str(uuid.uuid4())})
        response.raise_for_status();run_id=response.json()['initial_run']['id'];assert run_id not in previous
    deadline=time.monotonic()+135
    while time.monotonic()<deadline:
        detail=get('/api/local/dsh/runs/'+run_id)
        if detail['run']['status'] in {'succeeded','failed','cancelled','expired'}:break
        time.sleep(.5)
    assert detail['run']['status']=='succeeded',detail['run']
    assert detail['budget']['reserved']==0 and detail['budget']['calls']>0,detail['budget']
    events=[];cursor=0
    while True:
        page=get(f'/api/local/dsh/runs/{run_id}/events?after={cursor}')
        if not page['items']:break
        assert page['next_cursor']>cursor
        events.extend(page['items']);cursor=page['next_cursor']
    sequences=[e['sequence'] for e in events]
    assert len(sequences)==len(set(sequences)) and sequences==sorted(sequences)
    assert events[-1]['event_type']=='run.succeeded'
    artifacts=[];business_status=None
    for a in detail['artifacts']:
        r=client.get('/api/v1/artifacts/'+a['id']+'/content');r.raise_for_status()
        assert len(r.content)==a['size_bytes'] and hashlib.sha256(r.content).hexdigest()==a['sha256']
        artifacts.append({k:a[k] for k in ('id','name','size_bytes','sha256')})
        if a['name']=='dsh-findings.json':
            record=r.json();business_status=record['business_status']
            assert record['findings']['term']['status']=='supported'
            assert record['findings']['exception']['status']=='supported'
    assert business_status=='partial' and len(artifacts)>=2
    assert get('/api/local/dsh/runtime')['release']==release
    return dict(release=release,run_id=run_id,new_run=created,status=detail['run']['status'],budget=detail['budget'],
                events=len(events),artifacts=artifacts,business_status=business_status,
                real_provider_enabled=status['real_provider_enabled'],credential_ref_configured=status['credential_ref_configured'],
                real_provider_calls=0,artifact_hashes_verified=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--release',required=True)
    p.add_argument('--output',required=True);p.add_argument('--run-id');a=p.parse_args()
    with httpx.Client(base_url=a.base,trust_env=False,timeout=15) as client: result=verify(client,a.release,a.run_id)
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
