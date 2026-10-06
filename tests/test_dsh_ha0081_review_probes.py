"""mymaccodex review probes for HA-0081 @ 343a3b3, kept verbatim as regressions."""
import functools
import json
from backend.dsh_context import assemble
from test_dsh_context import STATE, payload, turn, call, LONG_DOC
from test_dsh_payment_findings import client, submit, reply

def test_duplicate_unresolved_call_is_rejected():
    from backend.analysis import Problem
    import pytest
    p = payload()
    p['messages'] += [
        {'role':'assistant','content':'','tool_calls':[call('same'),call('same')]},
        {'role':'tool','tool_call_id':'same','content':'[]'}]
    with pytest.raises(Problem):
        assemble(p, STATE)

def test_result_cannot_cross_a_new_user_message():
    from backend.analysis import Problem
    import pytest
    p=payload()
    p['messages'] += [
        {'role':'assistant','content':'','tool_calls':[call('x')]},
        {'role':'user','content':'interrupt'},
        {'role':'tool','tool_call_id':'x','content':'[]'}]
    with pytest.raises(Problem):
        assemble(p,STATE)

def test_full_current_copy_prevents_false_new_progress(client, monkeypatch):
    import backend.dsh_runtime as runtime
    # HA-0083: account for platform-issued tool IDs; the progress assertion is unchanged.
    monkeypatch.setattr(runtime, 'assemble_context', functools.partial(assemble, context_window=7100))
    ident=submit(client,template='free',document=LONG_DOC,key='independent-repeat')
    rt=client.app.state.service.dsh
    requests=[]
    async def provider(value,limit):
        requests.append(value)
        n=len(requests)
        if n<=4:
            return reply(calls=[('read_clause',{'clause_id':f'clause-{n}'})])
        if n<=7:
            return reply(calls=[('read_clause',{'clause_id':'clause-1'})])
        return reply('见 clause-1。')
    rt.send_probe=provider
    rt.execute(ident)
    detail=rt.detail(ident)
    evidence=[e['data'] for e in rt.store.events(ident) if e['event_type']=='dsh.tool.completed']
    print('REPEAT_RESULT',detail['run']['status'],detail['run']['exit_reason'],len(requests),[(e['clause_ids'],e['new_evidence']) for e in evidence])
    for n,p in enumerate(requests,1):
        full=[]
        for m in p['messages']:
            if m['role']!='tool': continue
            try: v=json.loads(m['content'])
            except ValueError: continue
            items=v if isinstance(v,list) else v.get('matches',[])
            full += [i['clause_id'] for i in items]
        print('REQUEST',n,'FULL',full)
    assert detail['run']['exit_reason']=='DSH_NO_PROGRESS'
