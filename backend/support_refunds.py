"""Synthetic order service exposed through the official MCP Server, no payment rails."""
from datetime import datetime, timedelta, timezone
import hmac
import json

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from .analysis import digest
from .store import dumps, now, uid
from .support_providers import fail


class DemoRefunds:
    def __init__(self, store, mcp):
        self.store,self.mcp=store,mcp
        with store.lock:
            store.db.executescript('''
                CREATE TABLE IF NOT EXISTS support_demo_orders(id TEXT PRIMARY KEY,doc TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS support_demo_refunds(id TEXT PRIMARY KEY,order_id TEXT NOT NULL,doc TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS support_demo_receipts(id TEXT PRIMARY KEY,doc TEXT NOT NULL);
            ''')
        with store.transaction() as db:
            for ident,days in [('DEMO-001',2),('DEMO-002',10),('DEMO-003',None)]:
                doc={'id':ident,'amount_minor':19900,'currency':'CNY','synthetic':True,
                     'signed_at':(datetime.now(timezone.utc)-timedelta(days=days)).isoformat() if days else None}
                db.execute('INSERT OR IGNORE INTO support_demo_orders VALUES(?,?)',(ident,dumps(doc)))

    def orders(self):
        with self.store.lock:
            return [json.loads(r[0]) for r in self.store.db.execute('SELECT doc FROM support_demo_orders ORDER BY id')]

    def eligibility(self, order_id):
        with self.store.lock:
            row=self.store.db.execute('SELECT doc FROM support_demo_orders WHERE id=?',(order_id,)).fetchone()
        if not row: return {'eligible':False,'reason':'ORDER_NOT_FOUND','synthetic':True}
        doc=json.loads(row[0]); signed=doc['signed_at']
        eligible=bool(signed) and datetime.now(timezone.utc)<=datetime.fromisoformat(signed)+timedelta(days=7)
        return {'eligible':eligible,'reason':'WITHIN_SEVEN_DAYS' if eligible else 'OUTSIDE_REFUND_WINDOW',
                'order':doc,'synthetic':True}

    def status(self, order_id='', refund_id=''):
        if bool(order_id)==bool(refund_id): return {'error':'SPECIFY_ONE_ID','synthetic':True}
        with self.store.lock:
            row=self.store.db.execute('SELECT doc FROM support_demo_refunds WHERE '+('id' if refund_id else 'order_id')+'=? ORDER BY rowid DESC LIMIT 1',
                                      (refund_id or order_id,)).fetchone()
        return {'refund':json.loads(row[0]) if row else None,'synthetic':True}

    def mutate(self, name, args, approval_id):
        with self.store.transaction() as db:
            action=self.mcp.approval(approval_id)
            server=self.mcp.get(action['server_id'],enabled=True)
            if (action['status']!='executing' or action['tool']!=name or action['expires']<__import__('time').time() or
                server['endpoint']!=self.mcp.demo_endpoint or server['revision']!=action['revision'] or
                action['arguments_sha256']!=digest(dumps(args).encode())):
                raise fail('SUPPORT_REFUND_APPROVAL_REQUIRED',403)
            old=db.execute('SELECT doc FROM support_demo_receipts WHERE id=?',(approval_id,)).fetchone()
            if old: return json.loads(old[0])
            if name=='submit_refund':
                check=self.eligibility(args['order_id'])
                if not check['eligible']: return check
                if db.execute("SELECT 1 FROM support_demo_refunds WHERE order_id=? AND json_extract(doc,'$.status') IN ('pending','approved')",(args['order_id'],)).fetchone():
                    return {'error':'REFUND_ALREADY_EXISTS','synthetic':True}
                doc={'id':uid('refund'),'order_id':args['order_id'],'status':'pending','reason':args['reason'],
                     'amount_minor':check['order']['amount_minor'],'created_at':now(),'updated_at':now(),'synthetic':True,
                     'note':'仅演示记录；没有真实退款或资金流转'}
                db.execute('INSERT INTO support_demo_refunds VALUES(?,?,?)',(doc['id'],doc['order_id'],dumps(doc)))
            else:
                row=db.execute('SELECT doc FROM support_demo_refunds WHERE id=?',(args['refund_id'],)).fetchone()
                if not row: return {'error':'REFUND_NOT_FOUND','synthetic':True}
                doc=json.loads(row[0])
                if doc['status']!='pending': return {'error':'REFUND_NOT_CANCELLABLE','synthetic':True}
                doc.update(status='cancelled',updated_at=now())
                db.execute('UPDATE support_demo_refunds SET doc=? WHERE id=?',(dumps(doc),doc['id']))
            result={'refund':doc,'synthetic':True}
            db.execute('INSERT INTO support_demo_receipts VALUES(?,?)',(approval_id,dumps(result)))
            return result


def make_demo_mcp(app, token):
    server=MCPServer('harness-synthetic-refunds',instructions='合成订单演示，不发生真实退款。写操作需要平台人工批准。')
    @server.tool()
    def check_refund_eligibility(order_id:str)->dict:
        """查询合成订单退款资格；签收7天以内可以申请。"""
        return app.state.support_refunds.eligibility(order_id)
    @server.tool()
    def get_refund_status(order_id:str='',refund_id:str='')->dict:
        """按订单或退款编号查询状态，二选一。"""
        return app.state.support_refunds.status(order_id,refund_id)
    @server.tool()
    def submit_refund(order_id:str,reason:str,approval_id:str='')->dict:
        """申请合成退款。平台会要求人工确认；不发生真实资金转移。"""
        if not 1<=len(reason)<=500: return {'error':'REASON_INVALID'}
        return app.state.support_refunds.mutate('submit_refund',{'order_id':order_id,'reason':reason},approval_id)
    @server.tool()
    def cancel_refund(refund_id:str,approval_id:str='')->dict:
        """取消合成退款申请；仅pending可以取消，需平台人工确认。"""
        return app.state.support_refunds.mutate('cancel_refund',{'refund_id':refund_id},approval_id)
    raw=server.streamable_http_app(json_response=True,stateless_http=True,max_request_body_size=32768,
        transport_security=TransportSecuritySettings(allowed_hosts=['127.0.0.1:*','localhost:*']))
    class Authorized:
        async def __call__(self,scope,receive,send):
            if scope['type']=='http':
                headers=dict(scope['headers'])
                supplied=headers.get(b'authorization',b'')
                if not hmac.compare_digest(supplied,('Bearer '+token).encode()):
                    await JSONResponse({'error':'MCP_UNAUTHORIZED'},status_code=403)(scope,receive,send)
                    return
                app.state.support_providers.require_enabled()
            await raw(scope,receive,send)
    return server,Authorized()
