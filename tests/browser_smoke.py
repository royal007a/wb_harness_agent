"""Run explicitly against a local deployment; creates a visible demonstration task."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(os.environ.get('HARNESS_BROWSER_EVIDENCE', ROOT / 'harness/evidence/HA-0006'))
OUTPUT.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1440, 'height': 1150}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
    page.goto(os.environ.get('HARNESS_TEST_URL', 'http://127.0.0.1:8765'))
    page.get_by_role('button', name='使用示例销售数据').click()
    expect(page.locator('#upload-title')).to_have_text('sales.csv')
    page.locator('#objective').fill('销售数据质量与数值概况 · 本地验收')
    page.get_by_role('button', name='预检分析意图').click()
    expect(page.locator('#intent-result')).to_contain_text('意图已就绪')
    page.screenshot(path=str(OUTPUT / 'intent-preflight.png'), full_page=True)
    page.get_by_role('button', name='创建并运行').click()
    expect(page.locator('#detail')).to_be_visible()
    expect(page.locator('.artifact-link')).to_have_count(3, timeout=15000)
    expect(page.locator('#tab-overview')).to_contain_text('12')
    page.get_by_role('tab', name='执行事件').click()
    expect(page.locator('#tab-events')).to_contain_text('run.succeeded')
    page.get_by_role('tab', name='权限与配置').click()
    expect(page.locator('#tab-policy')).to_contain_text('engine_mock_analytics')
    page.get_by_role('tab', name='分析结果').click()
    with page.expect_download() as download_info:
        page.get_by_role('link', name='report.md').click()
    assert download_info.value.suggested_filename == 'report.md'
    page.get_by_role('button', name='重新运行').click()
    expect(page.locator('#run-select option')).to_have_count(2)
    expect(page.locator('.artifact-link')).to_have_count(3, timeout=15000)
    page.get_by_role('button', name='数据资源', exact=True).click()
    expect(page.locator('#resource-table')).to_contain_text('sales.csv')
    page.get_by_role('button', name='引擎与能力', exact=True).click()
    expect(page.locator('.engine-card')).to_have_count(6)
    expect(page.locator('.engine-card').filter(has_text='Smolagents')).to_contain_text('待接入')
    page.screenshot(path=str(OUTPUT / 'engines-desktop.png'), full_page=True)
    page.get_by_role('button', name='分析工作台', exact=True).click()
    page.reload()
    expect(page.locator('.artifact-link')).to_have_count(3)
    page.screenshot(path=str(OUTPUT / 'workbench-desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    expect(page.locator('#create-form')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow'
    page.screenshot(path=str(OUTPUT / 'workbench-mobile.png'), full_page=True)
    assert not errors, errors
    report = {'browser': browser.version, 'errors': errors, 'checks': ['sample_upload', 'intent_preflight', 'create', 'artifacts', 'events', 'policy', 'download', 'rerun', 'resources', 'engines', 'model_route_blocked', 'reload', 'mobile_layout']}
    (OUTPUT / 'browser.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))
    browser.close()
