"""Browser verification for HA-0026; it only creates synthetic local tasks."""
import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


OUTPUT = Path(__file__).resolve().parents[1] / 'harness/evidence/HA-0026'
OUTPUT.mkdir(parents=True, exist_ok=True)
with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={'width': 1440, 'height': 1150})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
    page.goto(os.environ.get('HARNESS_TEST_URL', 'http://127.0.0.1:8765') + '/research-agents')
    expect(page.locator('.demo-banner')).to_contain_text('不是 Claude Agent SDK')
    page.locator('input[value=demo_b]').check()
    page.get_by_role('button', name='创建 Agent 模拟运行').click()
    expect(page.locator('#agent-root-status')).to_have_text('已完成', timeout=15000)
    expect(page.locator('.research-child')).to_have_count(6)
    expect(page.locator('#agent-summary')).to_contain_text('6 个已验证结果')
    expect(page.locator('#agent-summary')).to_contain_text('模型、Provider、网络和外部工具调用均为 0')
    with page.expect_download() as download:
        page.get_by_role('link', name='↓ research-agent-report.md').click()
    assert download.value.suggested_filename == 'research-agent-report.md'
    previous = page.locator('#agent-root-id').inner_text()
    page.get_by_role('button', name='重新运行', exact=True).click()
    expect(page.locator('#agent-root-id')).not_to_have_text(previous)
    expect(page.locator('#agent-root-status')).to_have_text('已完成')
    page.locator('input[value=demo_b]').uncheck()
    page.locator('#agent-scenario').select_option('missing_risk')
    page.get_by_role('button', name='创建 Agent 模拟运行').click()
    expect(page.locator('#agent-root-status')).to_have_text('完成 · 有证据缺口', timeout=15000)
    expect(page.locator('#agent-summary')).to_contain_text('1 个失败/取消')
    expect(page.locator('#agent-events')).to_contain_text('research.agent.aggregated')
    page.screenshot(path=str(OUTPUT / 'research-agents-desktop.png'), full_page=True)
    page.reload()
    expect(page.locator('#agent-root-status')).to_have_text('完成 · 有证据缺口')
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
    page.screenshot(path=str(OUTPUT / 'research-agents-mobile.png'), full_page=True)
    assert not errors, errors
    report = {'browser': browser.version, 'errors': errors, 'checks': [
        'clear_simulation_label', 'three_agent_fanout', 'zero_external_calls', 'artifact_download',
        'rerun_new_tree', 'partial_risk_failure', 'event_trace', 'reload', 'mobile_layout',
    ]}
    (OUTPUT / 'browser.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    browser.close()
