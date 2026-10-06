"""Official MCP client + server over real loopback HTTP, synthetic orders only."""
import asyncio
import json
import os
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from backend.app import create_app


@pytest.fixture
def live(tmp_path,monkeypatch):
    monkeypatch.setenv('HARNESS_SUPPORT','enabled')
    key=tmp_path/'master'; key.write_bytes(os.urandom(32)); key.chmod(0o600)
    monkeypatch.setenv('HARNESS_SUPPORT_MASTER_KEY_FILE',str(key))
    listener=socket.socket(); listener.bind(('127.0.0.1',0))
    base='http://127.0.0.1:'+str(listener.getsockname()[1])
    monkeypatch.setenv('HARNESS_SUPPORT_DEMO_MCP_URL',base+'/api/local/support/mcp-service/mcp')
    app=create_app(tmp_path/'mcp.db',run_worker=False)
    server=uvicorn.Server(uvicorn.Config(app,log_level='critical',access_log=False))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True); thread.start()
    try:
        deadline=time.monotonic()+10
        while not server.started and thread.is_alive() and time.monotonic()<deadline: time.sleep(.01)
        assert server.started
        with httpx.Client(base_url=base,trust_env=False,timeout=25) as client:
            yield client,app
    finally:
        server.should_exit=True; thread.join(10); listener.close()
        assert not thread.is_alive()


def setup(client):
    response=client.post('/api/local/support/mcp',json={'name':'退款演示','read_only_tools':['check_refund_eligibility','get_refund_status']})
    assert response.status_code==201,response.text
    ident=response.json()['id']
    response=client.post('/api/local/support/mcp/'+ident+'/discover',json={})
    assert response.status_code==200,response.text
    return response.json()


def invoke(client,server,name,arguments):
    r=client.post('/api/local/support/mcp/'+server['id']+'/debug',json={'name':name,'arguments':arguments})
    assert r.status_code==200,r.text
    return r.json()


def structured(result):
    return result.get('structuredContent') or json.loads(result['content'][0]['text'])


def test_official_mcp_discovery_refund_human_approval_and_cancel(live):
    c,app=live
    server=setup(c)
    assert len(server['tools'])==4
    assert all('approval_id' not in t['schema'].get('properties',{}) for t in server['tools'])
    assert c.post('/api/local/support/mcp-service/mcp',json={}).status_code==403
    assert structured(invoke(c,server,'check_refund_eligibility',{'order_id':'DEMO-001'}))['eligible']
    assert not structured(invoke(c,server,'check_refund_eligibility',{'order_id':'DEMO-002'}))['eligible']
    pending=invoke(c,server,'submit_refund',{'order_id':'DEMO-001','reason':'合成测试'})
    assert pending['executed'] is False
    assert structured(invoke(c,server,'get_refund_status',{'order_id':'DEMO-001'}))['refund'] is None
    r=c.post('/api/local/support/approvals/'+pending['approval_id']+'/decision',json={'decision':'approve'})
    assert r.status_code==200,r.text
    assert r.json()['status']=='succeeded',r.text
    refund=structured(r.json()['result'])['refund']
    assert refund['status']=='pending'
    assert c.post('/api/local/support/approvals/'+pending['approval_id']+'/decision',json={'decision':'approve'}).json()==r.json()
    cancel=invoke(c,server,'cancel_refund',{'refund_id':refund['id']})
    r=c.post('/api/local/support/approvals/'+cancel['approval_id']+'/decision',json={'decision':'approve'})
    assert structured(r.json()['result'])['refund']['status']=='cancelled'
    assert app.state.service.store.db.execute('SELECT COUNT(*) FROM support_demo_receipts').fetchone()[0]==2


def test_mcp_boundary_revision_and_agent_binding(live):
    c,app=live; server=setup(c)
    assert c.post('/api/local/support/mcp',json={'name':'bad','endpoint':'http://169.254.169.254/mcp'}).status_code==422
    assert c.put('/api/local/support/mcp/'+server['id'],json={'read_only_tools':['submit_refund']}).status_code==422
    assert c.post('/api/local/support/mcp/'+server['id']+'/debug',json={'name':'submit_refund','arguments':{'order_id':'DEMO-001','reason':'x','approval_id':'forged'}}).status_code==422
    p=app.state.support_providers.save({'name':'synthetic','api_key':'SYNTH_ONLY','auto_probe':False})
    tool=next(t['alias'] for t in server['tools'] if t['name']=='check_refund_eligibility')
    assert c.post('/api/local/support/agents',json={'name':'a','provider_id':p['id'],'tools':[tool]}).status_code==403
    a=c.post('/api/local/support/agents',json={'name':'a','provider_id':p['id'],'tools':[tool],'mcp_ids':[server['id']]}).json()
    session=c.post('/api/local/support/sessions',json={'agent_id':a['id']}).json()
    pending=invoke(c,server,'submit_refund',{'order_id':'DEMO-001','reason':'test'})
    c.put('/api/local/support/mcp/'+server['id'],json={'enabled':False})
    assert c.post('/api/local/support/approvals/'+pending['approval_id']+'/decision',json={'decision':'approve'}).status_code==409
    from backend.analysis import Problem
    with pytest.raises(Problem): app.state.support_mcp.validate_agent(session['agent'])
    assert app.state.support_refunds.status('DEMO-001')['refund'] is None


def test_model_tool_result_next_turn_and_explicit_confirmation(live):
    c,app=live; server=setup(c)
    alias=next(t['alias'] for t in server['tools'] if t['name']=='submit_refund')
    provider=app.state.support_providers.save({'name':'mock','api_key':'SYNTH_ONLY','auto_probe':False})
    a=c.post('/api/local/support/agents',json={'name':'refund','provider_id':provider['id'],'tools':[alias],'mcp_ids':[server['id']]}).json()
    s=c.post('/api/local/support/sessions',json={'agent_id':a['id']}).json()
    calls=[]
    async def model(providers,ident,payload):
        calls.append(payload)
        if len(calls)==1:
            message={'role':'assistant','content':'','tool_calls':[{'id':'t1','type':'function','function':{
                'name':alias,'arguments':json.dumps({'order_id':'DEMO-001','reason':'synthetic'})}}]}
        else:
            result=json.loads(payload['messages'][-1]['content'])
            assert result['approval_required'] and not result['executed']
            message={'role':'assistant','content':'请在平台审批面板确认；尚未退款。'}
        yield {'result':{'message':message,'usage':{'input_tokens':10,'output_tokens':10,'total_tokens':20}}}
    app.state.support_chat.stream_model=model
    r=c.post('/api/local/support/sessions/'+s['id']+'/messages',json={'content':'退订单DEMO-001'},headers={'Idempotency-Key':'k','Accept':'text/event-stream'})
    assert any(json.loads(line[6:])['type']=='done' for line in r.text.splitlines() if line.startswith('data: ')),r.text
    assert len(calls)==2
    assert app.state.support_refunds.status('DEMO-001')['refund'] is None
    approval=c.get('/api/local/support/approvals').json()['items'][0]
    assert approval['agent_id']==a['id']
    confirmed=c.post('/api/local/support/approvals/'+approval['id']+'/decision',json={'decision':'approve'})
    assert confirmed.json()['status']=='succeeded',confirmed.text
    assert app.state.support_refunds.status('DEMO-001')['refund']['status']=='pending'


def test_unknown_outcome_not_retried_and_reject_never_calls(live):
    c,app=live; server=setup(c)
    action=invoke(c,server,'submit_refund',{'order_id':'DEMO-001','reason':'synthetic'})
    calls=[]
    async def failed(*args,**kwargs): calls.append(1); raise TimeoutError()
    app.state.support_mcp.rpc=failed
    r=c.post('/api/local/support/approvals/'+action['approval_id']+'/decision',json={'decision':'approve'})
    assert r.json()['status']=='unknown'
    assert c.post('/api/local/support/approvals/'+action['approval_id']+'/decision',json={'decision':'approve'}).json()['status']=='unknown'
    assert len(calls)==1
    other=invoke(c,server,'submit_refund',{'order_id':'DEMO-001','reason':'other'})
    assert c.post('/api/local/support/approvals/'+other['approval_id']+'/decision',json={'decision':'reject'}).json()['status']=='rejected'
    assert len(calls)==1


@pytest.mark.parametrize('bad',[{'$ref':'https://example.com/schema'}, {'type':'object','properties':{'x':{'$ref':'file:///private'}}}])
def test_untrusted_remote_schema_rejected_before_registration(live,bad):
    c,app=live; server=setup(c)
    before=app.state.support_mcp.get(server['id'])
    async def remote(*a,**kw): return {'tools':[{'name':'evil','inputSchema':bad}]}
    app.state.support_mcp.rpc=remote
    r=c.post('/api/local/support/mcp/'+server['id']+'/discover',json={})
    assert r.status_code==502
    assert app.state.support_mcp.get(server['id'])==before


def test_mcp_browser_discover_debug_and_approval(live):
    pw=pytest.importorskip('playwright.sync_api')
    c,app=live
    with pw.sync_playwright() as driver:
        browser=driver.chromium.launch()
        page=browser.new_page(viewport={'width':390,'height':844})
        errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('dialog',lambda d:d.accept())
        page.goto(str(c.base_url)+'/support')
        page.get_by_role('button',name='MCP 与审批',exact=True).click()
        pw.expect(page.locator('#mcp-endpoint')).not_to_have_value('')
        page.get_by_role('button',name='保存 MCP',exact=True).click()
        pw.expect(page.locator('#mcp-list')).to_contain_text('合成退款服务')
        page.get_by_role('button',name='发现工具',exact=True).click()
        pw.expect(page.locator('#mcp-list')).to_contain_text('4 个工具')
        page.locator('#mcp-debug-tool').select_option(label='合成退款服务 / submit_refund')
        page.locator('#mcp-args').fill('{"order_id":"DEMO-001","reason":"浏览器合成测试"}')
        page.get_by_role('button',name='调用工具',exact=True).click()
        pw.expect(page.locator('#approvals')).to_contain_text('pending')
        assert app.state.support_refunds.status('DEMO-001')['refund'] is None
        page.get_by_role('button',name='确认执行',exact=True).click()
        pw.expect(page.locator('#approvals')).to_contain_text('succeeded')
        assert app.state.support_refunds.status('DEMO-001')['refund']['status']=='pending'
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert errors==[]
        browser.close()
