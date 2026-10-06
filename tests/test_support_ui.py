"""Real browser/server; synthetic Provider and vectors, no external request."""
import asyncio
import os
import socket
import threading
import time

import pytest
import uvicorn

from backend.app import create_app

pw = pytest.importorskip('playwright.sync_api')


def test_support_knowledge_agent_stream_and_mobile(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_SUPPORT', 'enabled')
    master = tmp_path/'master'
    master.write_bytes(os.urandom(32))
    master.chmod(0o600)
    monkeypatch.setenv('HARNESS_SUPPORT_MASTER_KEY_FILE', str(master))
    app = create_app(tmp_path/'ui.db', run_worker=False)
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic()+20
        while not server.started and thread.is_alive() and time.monotonic()<deadline: time.sleep(.01)
        assert server.started
        async def embed(texts): return [[1.0]+[0.0]*511 for _ in texts]
        app.state.support_knowledge.embed = embed
        calls = []
        async def stream(providers, ident, payload):
            calls.append(payload)
            assert '七天' in payload['messages'][0]['content']
            for part in ('合成测试：', '七天内未拆封可退货。'):
                yield {'delta': part}
                await asyncio.sleep(.01)
            yield {'result': {'message': {'role': 'assistant', 'content': '合成测试：七天内未拆封可退货。'},
                              'usage': {'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120}}}
        app.state.support_chat.stream_model = stream
        app.state.support_providers.save({'name': '合成供应商', 'api_key': 'UI_SYNTH_KEY', 'auto_probe': False})
        base = 'http://127.0.0.1:'+str(listener.getsockname()[1])
        with pw.sync_playwright() as driver:
            browser = driver.chromium.launch()
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(base+'/support')
            page.get_by_role('button', name='知识库', exact=True).click()
            page.locator('#knowledge-name').fill('退款政策')
            page.get_by_role('button', name='保存知识库').click()
            pw.expect(page.locator('#knowledge-title')).to_have_text('退款政策')
            page.locator('#document-name').fill('公开合成手册.txt')
            page.locator('#document-text').fill('## 退货政策\n七天内未拆封可退货。')
            page.get_by_role('button', name='上传并建立语义索引').click()
            pw.expect(page.locator('#documents')).to_contain_text('ready', timeout=10000)
            page.locator('#knowledge-query').fill('怎么退款？')
            page.get_by_role('button', name='语义检索', exact=True).click()
            pw.expect(page.locator('#knowledge-results')).to_contain_text('七天内')
            page.get_by_role('button', name='Agent', exact=True).click()
            page.locator('#agent-name').fill('售后客服')
            page.locator('#agent-knowledge').select_option(label='退款政策')
            page.get_by_role('button', name='保存 Agent', exact=True).click()
            pw.expect(page.locator('#agent-list')).to_contain_text('售后客服')
            page.get_by_role('button', name='客服对话', exact=True).click()
            page.get_by_role('button', name='新建会话', exact=True).click()
            pw.expect(page.locator('#session-title')).to_contain_text('售后客服')
            page.locator('#question').fill('退货条件是什么？')
            page.get_by_role('button', name='发送', exact=True).click()
            pw.expect(page.locator('#send')).to_be_enabled()
            pw.expect(page.locator('#messages')).to_contain_text('合成测试：七天内未拆封可退货。')
            pw.expect(page.locator('#messages summary')).to_contain_text('参考资料')
            assert len(calls) == 1
            page.reload()
            page.locator('#sessions button').first.click()
            pw.expect(page.locator('#messages')).to_contain_text('七天内未拆封可退货。')
            assert len(calls) == 1
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            # Create and bind an actual workflow through the JSON editor, then
            # execute the branch through the same durable chat endpoint.
            flow = {'nodes': [{'id': 'start', 'type': 'START', 'config': {}},
                {'id': 'route', 'type': 'CONDITION', 'config': {'left': '{{start.input}}', 'operator': 'contains', 'right': '退款'}},
                {'id': 'yes', 'type': 'END', 'config': {'text': '工作流退款分支：请提供订单号。'}},
                {'id': 'no', 'type': 'END', 'config': {'text': '其他分支'}}],
                'edges': [{'source': 'start', 'target': 'route', 'condition': None},
                          {'source': 'route', 'target': 'yes', 'condition': True},
                          {'source': 'route', 'target': 'no', 'condition': False}]}
            import json
            page.get_by_role('button', name='工作流', exact=True).click()
            page.locator('#workflow-name').fill('分流测试')
            page.locator('#workflow-json').fill(json.dumps(flow))
            page.get_by_role('button', name='保存工作流', exact=True).click()
            pw.expect(page.locator('#workflow-list')).to_contain_text('分流测试')
            page.get_by_role('button', name='Agent', exact=True).click()
            page.locator('#agent-list').get_by_role('button', name='编辑').click()
            page.locator('#agent-workflow').select_option(label='分流测试')
            page.get_by_role('button', name='保存 Agent', exact=True).click()
            pw.expect(page.locator('#status')).to_contain_text('Agent 已保存')
            page.get_by_role('button', name='客服对话', exact=True).click()
            page.get_by_role('button', name='新建会话', exact=True).click()
            pw.expect(page.locator('#messages .message')).to_have_count(0)
            page.locator('#question').fill('退款怎么办？')
            page.get_by_role('button', name='发送', exact=True).click()
            pw.expect(page.locator('#send')).to_be_enabled()
            pw.expect(page.locator('#messages')).to_contain_text('工作流退款分支：请提供订单号。')
            assert len(calls) == 1  # This graph has no model node.
            page.get_by_role('button', name='工作流', exact=True).click()
            page.get_by_role('button', name='执行记录', exact=True).click()
            pw.expect(page.locator('#workflow-runs')).to_contain_text('succeeded')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), page.evaluate("[...document.querySelectorAll('body *')].filter(e=>e.scrollWidth>e.clientWidth&&e.clientWidth>0).map(e=>({id:e.id,tag:e.tagName,width:e.clientWidth,scroll:e.scrollWidth}))")
            assert 'UI_SYNTH_KEY' not in page.content()
            assert not errors
            browser.close()
    finally:
        server.should_exit = True
        thread.join(10)
        listener.close()
        assert not thread.is_alive()
