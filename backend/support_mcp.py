"""Explicitly admitted MCP tools; write tools require a durable human decision."""
import asyncio
import copy
import json
import os
import re
import time

import httpx2
from jsonschema import Draft202012Validator
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .analysis import Problem, digest
from .store import dumps, now, uid
from .support_providers import fail


class BoundedTransport(httpx2.AsyncBaseTransport):
    """Reject redirects before the SDK can follow them; bound decoded-free bodies."""
    def __init__(self):
        self.inner = httpx2.AsyncHTTPTransport(retries=0,trust_env=False)

    async def handle_async_request(self, request):
        response = await self.inner.handle_async_request(request)
        if 300 <= response.status_code < 400 or 'content-encoding' in response.headers:
            await response.aclose()
            raise fail('SUPPORT_MCP_TRANSPORT', 502)
        original = response.stream
        class Stream(httpx2.AsyncByteStream):
            async def __aiter__(self):
                size = 0
                async for part in original:
                    size += len(part)
                    if size > 262144: raise fail('SUPPORT_MCP_OUTPUT_LIMIT', 502)
                    yield part
            async def aclose(self):
                await original.aclose()
        response.stream = Stream()
        return response

    async def aclose(self):
        await self.inner.aclose()


class SupportMCP:
    def __init__(self, store, providers, chat, *, demo_token):
        self.store, self.providers, self.chat = store, providers, chat
        self.demo_token = demo_token
        self.demo_endpoint = os.getenv('HARNESS_SUPPORT_DEMO_MCP_URL', 'http://127.0.0.1:8765/api/local/support/mcp-service/mcp')
        self.endpoints = {self.demo_endpoint} | {v.strip() for v in os.getenv('HARNESS_SUPPORT_MCP_ENDPOINTS', '').split(',') if v.strip()}
        self.rpc = self._rpc
        self.leases = set()
        with store.lock:
            store.db.executescript('''
                CREATE TABLE IF NOT EXISTS support_mcp_servers(id TEXT PRIMARY KEY,doc TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS support_approvals(id TEXT PRIMARY KEY,doc TEXT NOT NULL);
            ''')
        for server in self.listing(): self.register(server)
        with store.transaction() as db:
            for row in db.execute('SELECT id,doc FROM support_approvals').fetchall():
                doc = json.loads(row['doc'])
                if doc['status'] == 'executing':
                    doc.update(status='unknown', error_code='SUPPORT_RESTARTED', updated_at=now())
                    db.execute('UPDATE support_approvals SET doc=? WHERE id=?', (dumps(doc), row['id']))

    def get(self, ident, enabled=False):
        with self.store.lock:
            row = self.store.db.execute('SELECT doc FROM support_mcp_servers WHERE id=?', (ident,)).fetchone()
        if not row: raise fail('SUPPORT_MCP_NOT_FOUND', 404)
        doc = json.loads(row[0])
        if enabled and not doc['enabled']: raise fail('SUPPORT_MCP_DISABLED', 409)
        return doc

    def listing(self):
        with self.store.lock:
            return [json.loads(r[0]) for r in self.store.db.execute('SELECT doc FROM support_mcp_servers ORDER BY rowid DESC')]

    def save(self, body, ident=None):
        self.providers.require_enabled()
        if not isinstance(body, dict) or set(body)-{'name','endpoint','enabled','read_only_tools'}:
            raise fail('SUPPORT_MCP_INVALID')
        with self.store.transaction() as db:
            old = self.get(ident) if ident else {}
            doc = {k: body.get(k, old.get(k, v)) for k,v in {'name':'','endpoint':self.demo_endpoint,'enabled':True,'read_only_tools':[]}.items()}
            if (not isinstance(doc['name'],str) or not 1<=len(doc['name'])<=100 or
                not isinstance(doc['endpoint'],str) or doc['endpoint'] not in self.endpoints or type(doc['enabled']) is not bool or
                not isinstance(doc['read_only_tools'],list) or len(doc['read_only_tools'])>16 or
                any(not isinstance(n,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,35}',n) for n in doc['read_only_tools'])):
                raise fail('SUPPORT_MCP_INVALID')
            # Demo mutations cannot be relabelled "read-only", even by its client configuration.
            if doc['endpoint']==self.demo_endpoint and set(doc['read_only_tools'])-{'check_refund_eligibility','get_refund_status'}:
                raise fail('SUPPORT_MCP_READ_POLICY')
            if ident in self.leases: raise fail('SUPPORT_MCP_BUSY',409)
            doc.update(id=ident or uid('mcp'),tools=old.get('tools',[]) if doc['endpoint']==old.get('endpoint') else [],revision=uid('v'),updated_at=now())
            if not ident and len(self.listing())>=16: raise fail('SUPPORT_MCP_LIMIT',409)
            db.execute('INSERT INTO support_mcp_servers VALUES(?,?) ON CONFLICT(id) DO UPDATE SET doc=excluded.doc',(doc['id'],dumps(doc)))
        self.register(doc)
        return doc

    def delete(self, ident):
        with self.store.transaction() as db:
            self.get(ident)
            if ident in self.leases: raise fail('SUPPORT_MCP_BUSY',409)
            db.execute('DELETE FROM support_mcp_servers WHERE id=?',(ident,))
        self.register({'id':ident,'tools':[]})
        return {'deleted':True}

    async def _rpc(self, server, operation, name=None, arguments=None):
        if server['endpoint'] not in self.endpoints: raise fail('SUPPORT_MCP_ENDPOINT_DENIED',403)
        headers={'Accept-Encoding':'identity'}
        if server['endpoint']==self.demo_endpoint: headers['Authorization']='Bearer '+self.demo_token
        try:
            async with asyncio.timeout(15):
                async with httpx2.AsyncClient(headers=headers,trust_env=False,follow_redirects=False,
                    timeout=10,transport=BoundedTransport()) as http:
                    async with streamable_http_client(server['endpoint'],http_client=http) as streams:
                        async with ClientSession(*streams,read_timeout_seconds=10) as session:
                            await session.initialize()
                            result = await session.list_tools() if operation=='list' else await session.call_tool(name,arguments)
                            return result.model_dump(mode='json',by_alias=True,exclude_none=True)
        except asyncio.CancelledError: raise
        except Exception: raise fail('SUPPORT_MCP_CALL_FAILED',502) from None

    async def discover(self, ident):
        self.providers.require_enabled()
        server=self.get(ident,enabled=True)
        if ident in self.leases: raise fail('SUPPORT_MCP_BUSY',409)
        self.leases.add(ident)
        try:
            value=await self.rpc(server,'list')
            raw=value.get('tools',[])
            if value.get('nextCursor') or not isinstance(raw,list) or not 1<=len(raw)<=16:
                raise fail('SUPPORT_MCP_SCHEMA_INVALID',502)
            tools=[]
            def refs(node,depth=0):
                if depth>16: raise fail('SUPPORT_MCP_SCHEMA_INVALID',502)
                if isinstance(node,dict):
                    if any(k in node for k in ('$ref','$dynamicRef','$id')): raise fail('SUPPORT_MCP_SCHEMA_INVALID',502)
                    for v in node.values(): refs(v,depth+1)
                elif isinstance(node,list):
                    for v in node: refs(v,depth+1)
            for item in raw:
                name=item.get('name'); schema=copy.deepcopy(item.get('inputSchema'))
                if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,35}',name):
                    raise fail('SUPPORT_MCP_SCHEMA_INVALID',502)
                if not isinstance(schema,dict) or schema.get('type')!='object' or len(dumps(schema))>12000:
                    raise fail('SUPPORT_MCP_SCHEMA_INVALID',502)
                refs(schema)
                if server['endpoint']==self.demo_endpoint:
                    schema.get('properties',{}).pop('approval_id',None)
                    schema['required']=[k for k in schema.get('required',[]) if k!='approval_id']
                schema['additionalProperties']=False
                try: Draft202012Validator.check_schema(schema)
                except Exception: raise fail('SUPPORT_MCP_SCHEMA_INVALID',502) from None
                description=item.get('description','')
                if not isinstance(description,str): raise fail('SUPPORT_MCP_SCHEMA_INVALID',502)
                tools.append({'name':name,'alias':'mcp_'+server['id'][-12:]+'_'+name,'description':description[:600], 'schema':schema})
            if len({t['name'] for t in tools})!=len(tools) or len(dumps(tools))>32000:
                raise fail('SUPPORT_MCP_SCHEMA_INVALID',502)
            server.update(tools=tools,revision=uid('v'),updated_at=now())
            with self.store.transaction() as db:
                db.execute('UPDATE support_mcp_servers SET doc=? WHERE id=?',(dumps(server),ident))
            self.register(server)
            return server
        finally: self.leases.discard(ident)

    def register(self, server):
        prefix='mcp_'+server['id'][-12:]+'_'
        for name in list(self.chat.tools.entries):
            if name.startswith(prefix): self.chat.tools.entries.pop(name)
        for tool in server['tools']:
            async def call(args,agent,context,tool=tool,ident=server['id']):
                self.validate_agent(agent)
                if ident not in agent['mcp_ids']: raise fail('SUPPORT_MCP_DENIED',403)
                return await self.invoke(ident,tool['name'],args,context,agent=agent)
            self.chat.tools.register(tool['alias'],tool['description'],tool['schema'],call)

    def validate_agent(self, agent):
        frozen=agent.get('mcp_snapshot',{})
        for ident in agent['mcp_ids']:
            server=self.get(ident,enabled=True)
            if frozen and frozen.get(ident)!=server['revision']: raise fail('SUPPORT_MCP_CHANGED',409)
        allowed={t['alias'] for ident in agent['mcp_ids'] for t in self.get(ident)['tools']}
        if any(n.startswith('mcp_') and n not in allowed for n in agent['tools']): raise fail('SUPPORT_MCP_DENIED',403)

    async def invoke(self, ident, name, arguments, context, agent=None):
        self.providers.require_enabled()
        server=self.get(ident,enabled=True)
        tool=next((t for t in server['tools'] if t['name']==name),None)
        if not tool or not Draft202012Validator(tool['schema']).is_valid(arguments):
            raise fail('SUPPORT_MCP_ARGUMENTS_INVALID')
        if name not in server['read_only_tools']:
            doc={'id':uid('approval'),'server_id':ident,'revision':server['revision'],'tool':name,
                 'arguments':arguments,'arguments_sha256':digest(dumps(arguments).encode()),'status':'pending',
                 'context':context,'agent_id':agent['id'] if agent else None,'expires':time.time()+600,
                 'created_at':now(),'updated_at':now(),'result':None}
            with self.store.transaction() as db:
                db.execute('INSERT INTO support_approvals VALUES(?,?)',(doc['id'],dumps(doc)))
            return {'approval_required':True,'approval_id':doc['id'],'status':'pending','executed':False}
        result=await self.rpc(server,'call',name,arguments)
        if len(dumps(result).encode())>24000: raise fail('SUPPORT_MCP_OUTPUT_LIMIT',502)
        return result

    def approvals(self):
        with self.store.lock:
            return [json.loads(r[0]) for r in self.store.db.execute('SELECT doc FROM support_approvals ORDER BY rowid DESC LIMIT 200')]

    def approval(self, ident):
        with self.store.lock: row=self.store.db.execute('SELECT doc FROM support_approvals WHERE id=?',(ident,)).fetchone()
        if row is None: raise fail('SUPPORT_APPROVAL_NOT_FOUND',404)
        return json.loads(row[0])

    def _approval_save(self, db, doc):
        doc['updated_at']=now()
        db.execute('UPDATE support_approvals SET doc=? WHERE id=?',(dumps(doc),doc['id']))

    async def decide(self, ident, decision):
        self.providers.require_enabled()
        if decision not in {'approve','reject'}: raise fail('SUPPORT_APPROVAL_INVALID')
        with self.store.transaction() as db:
            doc=self.approval(ident)
            if doc['status']!='pending': return doc
            if decision=='reject':
                doc['status']='rejected'; self._approval_save(db,doc); return doc
            if doc['expires']<time.time(): raise fail('SUPPORT_APPROVAL_EXPIRED',409)
            server=self.get(doc['server_id'],enabled=True)
            if server['revision']!=doc['revision']: raise fail('SUPPORT_MCP_CHANGED',409)
            if doc['agent_id']:
                agent=self.chat.get('agents',doc['agent_id'])
                session=self.chat.get('sessions',doc['context']['session_id'])
                if not agent['enabled']: raise fail('SUPPORT_AGENT_DISABLED',409)
                self.validate_agent(session['agent'])
                exchange=self.chat.get('exchanges',doc['context']['exchange_id'])
                if exchange['status']!='succeeded': raise fail('SUPPORT_APPROVAL_EXCHANGE_NOT_SUCCEEDED',409)
            if doc['server_id'] in self.leases: raise fail('SUPPORT_MCP_BUSY',409)
            self.leases.add(doc['server_id'])
            doc['status']='executing'; self._approval_save(db,doc)
        args=copy.deepcopy(doc['arguments'])
        if server['endpoint']==self.demo_endpoint: args['approval_id']=ident
        try:
            result=await self.rpc(server,'call',doc['tool'],args)
            if len(dumps(result).encode())>24000: raise fail('SUPPORT_MCP_OUTPUT_LIMIT',502)
            doc.update(status='failed' if result.get('isError') else 'succeeded',result=result)
        except BaseException as exc:
            doc.update(status='unknown',error_code='SUPPORT_MCP_OUTCOME_UNKNOWN')
            with self.store.transaction() as db: self._approval_save(db,doc)
            if isinstance(exc,asyncio.CancelledError): raise
            return doc
        finally: self.leases.discard(doc['server_id'])
        with self.store.transaction() as db: self._approval_save(db,doc)
        return doc
