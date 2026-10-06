"""Ephemeral Basic user for existing132 nginx acceptance; no secrets in argv/logs."""
import base64
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys

import httpx
from playwright.sync_api import sync_playwright,expect

REMOTE=r'''
import fcntl,json,os,sys
from pathlib import Path
p=Path('/etc/nginx/.htpasswd-harnessagent')
v=json.load(sys.stdin)
assert v['user'].startswith('ha0090_acceptance_') and ':' not in v['user']
with p.open('r+') as f:
 fcntl.flock(f,fcntl.LOCK_EX)
 lines=f.read().splitlines()
 lines=[line for line in lines if line.split(':',1)[0]!=v['user']]
 if v['action']=='add':lines.append(v['user']+':'+v['hash'])
 f.seek(0);f.write('\n'.join(lines)+'\n');f.truncate();f.flush();os.fsync(f.fileno())
print('ok')
'''

def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
    user='ha0090_acceptance_'+secrets.token_hex(8);password=secrets.token_urlsafe(32)
    hashed='{SHA}'+base64.b64encode(hashlib.sha1(password.encode()).digest()).decode()
    def remote(action):
        # Script is public code; password/hash only pass through encrypted stdin.
        command='python3 -c '+__import__('shlex').quote(REMOTE)
        r=subprocess.run(['ssh','-o','BatchMode=yes','root@118.196.123.132',command],input=json.dumps({'action':action,'user':user,'hash':hashed if action=='add' else ''}),text=True,capture_output=True)
        if r.returncode:raise RuntimeError('Ephemeral auth update failed (details withheld)')
    remote('add')
    try:
        base='http://118.196.123.132/harness'
        with httpx.Client(trust_env=False,timeout=20) as c:
            assert c.get(base+'/support').status_code==401
            c.auth=(user,password)
            r=c.get(base+'/support');assert r.status_code==200
            assert '/harness/static/support.js' in r.text
            for name in ['support.js','support.css','support-knowledge.js','support-workflows.js','support-mcp.js']:
                assert c.get(base+'/static/'+name).status_code==200,name
            status=c.get(base+'/api/local/support/status').json();assert status['enabled']
            assert c.post(base+'/api/local/support/providers',json={'name':'MUST_NOT_CREATE','api_key':'SYNTHETIC_TRANSPORT_TEST'}).status_code==403
            assert c.post(base+'/api/local/support/mcp-service/mcp',json={}).status_code==403
        with sync_playwright() as driver:
            browser=driver.chromium.launch()
            context=browser.new_context(http_credentials={'username':user,'password':password},viewport={'width':1280,'height':900})
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            assert page.goto(base+'/support').status==200
            expect(page.locator('#runtime')).to_contain_text('客服已启用')
            expect(page.locator('#sessions button').first).to_be_visible()
            page.locator('#sessions button').first.click();expect(page.locator('#messages .message')).not_to_have_count(0)
            page.screenshot(path=str(out/'remote-chat.png'),full_page=True)
            for title in ['Agent','知识库','工作流','MCP 与审批','模型与凭证']:
                page.get_by_role('button',name=title,exact=True).click()
            page.set_viewport_size({'width':390,'height':844})
            for title in ['客服对话','Agent','知识库','工作流','MCP 与审批','模型与凭证']:
                page.get_by_role('button',name=title,exact=True).click()
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),title
            page.screenshot(path=str(out/'remote-mobile.png'),full_page=True)
            assert not errors,errors
            browser.close()
        receipt={'url':base+'/support','status':status,'unauthenticated':401,'authenticated':200,
            'credential_write_over_plain_http':403,'mcp_without_capability':403,'page_errors':errors,'mobile_no_overflow':True}
    finally:remote('remove')
    receipt['temporary_auth_removed']=True
    (out/'result.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt))

if __name__=='__main__':main()
