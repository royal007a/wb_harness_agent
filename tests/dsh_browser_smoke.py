"""Explicit local deployment smoke. Uses synthetic document; real mode only with flag."""
import hashlib
import json
import os
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

base = os.environ.get('HARNESS_DSH_TEST_URL', 'http://127.0.0.1:8876')
out = Path(os.environ.get('HARNESS_DSH_BROWSER_EVIDENCE', 'harness/evidence/HA-0077'))
out.mkdir(parents=True, exist_ok=True)
report = {'base': base, 'runs': [], 'errors': []}
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1440, 'height': 1050})
    page.on('pageerror', lambda e: report['errors'].append(str(e)))
    page.goto(base + '/dsh')
    expect(page.locator('#runtime-state')).to_contain_text('官方 DSH 运行时已安装')
    expect(page.locator('#mode')).to_have_value('integration_probe')
    previous_count = len(page.request.get(base + '/api/local/dsh/runs').json()['items'])
    for mode in ['integration_probe'] + (['real_provider'] if os.getenv('HARNESS_DSH_TEST_REAL') == '1' else []):
        page.select_option('#mode', mode)
        page.locator('#objective').fill('这是合成合同。请先 read_clause 读取 clause-1，回答验收后多少天付款，并引用该证据块。')
        page.locator('#document').fill('合成合同测试：甲方验收后30天付款。乙方提供发票。')
        page.locator('#public-confirm').check()
        with page.expect_response(lambda r: r.url.endswith('/api/local/dsh/runs') and r.request.method == 'POST') as response:
            page.locator('#start').click()
        assert response.value.status == 201
        run_id = response.value.json()['initial_run']['id']
        expect(page.locator('#run-summary')).to_contain_text(re.compile('已完成|失败|已取消|已超时'), timeout=120000)
        expect(page.locator('#run-summary')).to_contain_text('已完成')
        expect(page.locator('#result')).to_contain_text('30', timeout=10000)
        expect(page.locator('#result')).to_contain_text('clause-1')
        expect(page.locator('#cancel')).to_be_hidden()
        detail = page.request.get(base + '/api/local/dsh/runs/' + run_id).json()
        assert detail['mode'] == mode and detail['run']['status'] == 'succeeded'
        assert detail['budget']['reserved'] == 0
        with page.expect_download() as download:
            page.get_by_role('link', name='下载分析产物').click()
        assert download.value.suggested_filename == 'dsh-analysis.txt'
        report['runs'].append({'id': run_id, 'mode': mode, 'status': detail['run']['status'],
                              'budget': detail['budget'], 'artifacts': detail['artifacts'],
                              'answer_sha256': hashlib.sha256(page.locator('#result').inner_text().encode()).hexdigest()})
    page.screenshot(path=str(out / 'dsh-desktop.png'), full_page=True)
    page.reload()
    expect(page.locator('#history button')).to_have_count(previous_count + len(report['runs']))
    page.locator('#history button').first.click()
    expect(page.locator('#result')).to_contain_text('30')
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(out / 'dsh-mobile.png'), full_page=True)
    report['release'] = page.request.get(base + '/api/local/dsh/runtime').json()['release']
    report['browser'] = browser.version
    assert report['errors'] == []
    browser.close()
(out / 'browser.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False))
