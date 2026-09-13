"""Browser verification for the unconfigured, safe OAuth connector surface."""
import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

OUTPUT = Path(__file__).resolve().parents[1] / 'harness/evidence/HA-0010'
OUTPUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
    page.goto(os.environ.get('HARNESS_TEST_URL', 'http://127.0.0.1:8765') + '/connectors/baidu-netdisk')
    expect(page.get_by_role('heading', name='连接已授权的百度网盘。')).to_be_visible()
    expect(page.get_by_text('官方 OAuth', exact=False)).to_be_visible()
    expect(page.locator('#state-badge')).to_have_text('未配置')
    expect(page.get_by_role('button', name='生成官方授权链接 ↗')).to_be_disabled()
    expect(page.get_by_text('不会读取浏览器 Cookie')).to_be_visible()
    expect(page.get_by_text('文件数据面')).to_be_visible()
    page.screenshot(path=str(OUTPUT / 'baidu-netdisk-desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
    page.screenshot(path=str(OUTPUT / 'baidu-netdisk-mobile.png'), full_page=True)
    assert not errors, errors
    report = {'browser': browser.version, 'errors': errors,
              'checks': ['unconfigured_status', 'authorization_disabled', 'oauth_boundary_copy', 'data_plane_disabled', 'mobile_layout']}
    (OUTPUT / 'browser.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    browser.close()
