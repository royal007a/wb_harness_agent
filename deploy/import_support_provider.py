"""Import an operator-authorized credential in memory via loopback, never argv/logs."""
import argparse
import json
import sys
from urllib.parse import urlsplit
import urllib.request


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--url',default='http://127.0.0.1:8765')
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--keychain-ref')
    source.add_argument('--stdin',action='store_true')
    args=p.parse_args()
    u=urlsplit(args.url)
    if u.scheme!='http' or u.hostname!='127.0.0.1' or u.username or u.password or u.path or u.query or u.fragment:
        raise SystemExit('Only direct loopback permitted')
    if args.keychain_ref:
        import keyring
        secret=keyring.get_password('harnessagent',args.keychain_ref)
    else: secret=sys.stdin.read(4096).strip()
    if not secret or len(secret)>2048: raise SystemExit('Credential unavailable')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(path,body=None,method=None):
        req=urllib.request.Request(args.url+'/api/local/support'+path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json'},method=method)
        with opener.open(req,timeout=15) as response:return json.load(response)
    existing=next((p for p in request('/providers')['items'] if p['name']=='Ark 客服模型'),None)
    body={'name':'Ark 客服模型','base_url':'https://ark.cn-beijing.volces.com/api/coding/v3',
          'model':'doubao-seed-2.1-lite','api_key':secret,'enabled':True,'auto_probe':True,'probe_interval_seconds':900}
    try:
        provider=request('/providers'+('/'+existing['id'] if existing else ''),body,'PUT' if existing else 'POST')
    except Exception: raise SystemExit('Credential import failed; inspect redacted service status') from None
    secret=None;body.pop('api_key',None)
    agents=request('/agents')['items']
    agent=next((a for a in agents if a['name']=='客服助手'),None)
    if not agent:
        agent=request('/agents',{'name':'客服助手','provider_id':provider['id'],
            'system_prompt':'你是客服助手。只依据提供的知识与工具结果回答业务事实；资料不足时说明不知道。工具返回待确认时，提示用户在MCP与审批面板确认，不能声称执行成功。内置退款仅为合成演示。'})
    print(json.dumps({'imported':True,'provider_id':provider['id'],'agent_id':agent['id'],
        'storage':'sqlite_aes_256_gcm','auto_probe':True}))


if __name__=='__main__':main()
