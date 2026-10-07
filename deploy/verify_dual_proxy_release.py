"""HA-0116 authenticated HTTPS UI check with a finally-removed temporary Basic user."""
import base64,hashlib,json,secrets,shlex,subprocess,sys
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
from verify_dsh_release import verify,DOCUMENT

REMOTE=r'''
import fcntl,json,os,sys
from pathlib import Path
p=Path('/etc/nginx/.htpasswd-harnessagent');v=json.load(sys.stdin)
assert v['user'].startswith('ha0116_acceptance_') and ':' not in v['user']
with p.open('r+') as f:
 fcntl.flock(f,fcntl.LOCK_EX)
 lines=[x for x in f.read().splitlines() if x.split(':',1)[0]!=v['user']]
 if v['action']=='add':lines.append(v['user']+':'+v['hash'])
 f.seek(0);f.write('\n'.join(lines)+'\n');f.truncate();f.flush();os.fsync(f.fileno())
'''

def main():
 out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
 user='ha0116_acceptance_'+secrets.token_hex(8);password=secrets.token_urlsafe(32)
 hashed='{SHA}'+base64.b64encode(hashlib.sha1(password.encode()).digest()).decode()
 def remote(action):
  p=subprocess.run(['ssh','-o','BatchMode=yes','root@118.196.123.132','python3 -c '+shlex.quote(REMOTE)],input=json.dumps(dict(action=action,user=user,hash=hashed if action=='add' else '')),text=True,capture_output=True)
  if p.returncode:raise RuntimeError('Temporary auth update failed; details withheld')
 support='https://118.196.123.132/harness';dsh='https://dsh.118.196.123.132.nip.io'
 receipt={'tls_verification':'existing self-signed certificate; verification disabled for acceptance','real_provider_calls':0}
 remote('add')
 try:
  with httpx.Client(verify=False,trust_env=False,timeout=20) as c:
   assert c.get(support+'/support').status_code==401
   assert c.get(dsh+'/dsh').status_code==401
   redirect=c.get(dsh.replace('https:','http:')+'/dsh');assert redirect.status_code==308 and redirect.headers['location']==dsh+'/dsh'
   c.auth=(user,password)
   for base,path,assets in [(support,'/support',['support.js','support.css','support-knowledge.js','support-workflows.js','support-mcp.js']),(dsh,'/dsh',['dsh.js','dsh.css'])]:
    assert c.get(base+path).status_code==200
    for name in assets:assert c.get(base+'/static/'+name).status_code==200,name
   status=c.get(support+'/api/local/support/status').json();assert status['release']=='561a6056ce180ea11c73b3f6ffde0615bb4eb539' and status['provider_count']==1
   receipt['support']=status
   assert c.get(dsh+'/api/local/external-skills/packages').status_code==403
   receipt['unauthenticated']=401;receipt['authenticated']=200;receipt['dsh_http_redirect']=308
  with sync_playwright() as driver:
   browser=driver.chromium.launch()
   context=browser.new_context(ignore_https_errors=True,http_credentials={'username':user,'password':password},viewport={'width':1280,'height':900})
   page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   assert page.goto(support+'/support').status==200
   expect(page.locator('#runtime')).to_contain_text('客服已启用')
   for name in ['Agent','知识库','工作流','MCP 与审批','模型与凭证','客服对话']:
    page.get_by_role('button',name=name,exact=True).click()
   page.screenshot(path=str(out/'support.png'),full_page=True)
   assert page.goto(dsh+'/dsh').status==200
   expect(page.locator('#runtime-state')).to_contain_text('官方 DSH 运行时已安装')
   expect(page.locator('#version')).to_contain_text('da43bff')
   if len(sys.argv)>2:
    run_id=sys.argv[2]
    page.locator('#history button').filter(has_text=run_id[-10:]).click()
   else:
    page.select_option('#template','payment_terms');page.fill('#document',DOCUMENT);page.check('#public-confirm')
    with page.expect_response(lambda r:r.request.method=='POST' and r.url==dsh+'/api/local/dsh/runs') as response:
     page.locator('#start').click()
    value=response.value;assert value.status==201;run_id=value.json()['initial_run']['id']
   expect(page.locator('#run-summary')).to_contain_text('已完成',timeout=135000)
   expect(page.locator('#history button').filter(has_text=run_id[-10:])).to_contain_text('已完成')
   expect(page.locator('#findings-status')).to_contain_text('部分结果')
   expect(page.locator('#form-message')).to_be_empty()
   page.screenshot(path=str(out/'dsh.png'),full_page=True)
   page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(out/'dsh-mobile.png'),full_page=True)
   receipt['dsh_mobile_overflow']=page.evaluate('document.documentElement.scrollWidth>innerWidth')
   assert not errors,errors
   receipt['page_errors']=errors;browser.close()
  with httpx.Client(base_url=dsh,verify=False,trust_env=False,timeout=20,auth=(user,password)) as c:
   receipt['dsh_browser_run']=verify(c,'da43bff8caf66ca528c85e81d81b28869c1cb9a4',run_id)
 finally:remote('remove')
 receipt['temporary_auth_removed']=True
 (out/'result.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False))

if __name__=='__main__':main()
