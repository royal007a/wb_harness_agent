"""Browser acceptance for ADR-0021; runs against the explicitly supplied local deployment."""
import json
import os
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(os.environ.get('HARNESS_AGENT_LAB_BROWSER_EVIDENCE', ROOT / 'harness/evidence/HA-0024'))
OUTPUT.mkdir(parents=True, exist_ok=True)
suffix = str(int(time.time() * 1000))
with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={'width': 1440, 'height': 1050}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
    page.goto(os.environ.get('HARNESS_TEST_URL', 'http://127.0.0.1:8765') + '/agent-lab')
    expect(page.locator('#runtime')).to_contain_text('模型、Provider、网络和工具调用均为 0')
    page.locator('#provider-form input[name=name]').fill('浏览器 Provider ' + suffix)
    page.locator('#provider-form input[name=base_url]').fill('https://example.invalid')
    page.get_by_role('button', name='保存 Provider').click()
    expect(page.locator('#provider-list')).to_contain_text('浏览器 Provider ' + suffix)
    page.locator('#model-provider').select_option(index=1)
    page.locator('#model-form input[name=display_name]').fill('浏览器模型 ' + suffix)
    page.locator('#model-form input[name=model_id]').fill('browser-model-' + suffix)
    page.get_by_role('button', name='保存 Model').click()
    expect(page.locator('#model-list')).to_contain_text('浏览器模型 ' + suffix)
    page.locator('#agent-model').select_option(index=1)
    page.locator('#agent-form input[name=name]').fill('浏览器 Agent ' + suffix)
    page.locator('#agent-form textarea[name=description]').fill('浏览器端到端本地演示。')
    page.get_by_role('button', name='保存 Agent').click()
    expect(page.locator('#agent-list')).to_contain_text('浏览器 Agent ' + suffix)
    page.locator('#session-agent').select_option(label='浏览器 Agent ' + suffix)
    page.get_by_role('button', name='新建会话').click()
    expect(page.locator('#chat-form')).to_be_visible()
    page.locator('#chat-input').fill('请验证 POST SSE。')
    page.get_by_role('button', name='发送').click()
    expect(page.locator('.bubble.assistant').last).to_contain_text('本地演示已完成', timeout=10000)
    expect(page.locator('.bubble.assistant').last).to_contain_text('不是模型对问题的实际回答')
    page.screenshot(path=str(OUTPUT / 'agent-lab-desktop.png'), full_page=True)
    page.locator('#chat-input').fill('这条消息用于停止显示。')
    page.get_by_role('button', name='发送').click()
    expect(page.get_by_role('button', name='停止')).to_be_visible()
    page.get_by_role('button', name='停止').click()
    expect(page.get_by_role('button', name='发送')).to_be_enabled()
    page.reload()
    expect(page.locator('#session-list')).to_contain_text('本地演示')
    page.set_viewport_size({'width': 390, 'height': 844})
    expect(page.locator('#new-session')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow'
    page.screenshot(path=str(OUTPUT / 'agent-lab-mobile.png'), full_page=True)
    assert not errors, errors
    report = {
        'browser': browser.version,
        'errors': errors,
        'checks': ['zero_call_runtime', 'provider_profile', 'model_profile', 'agent_profile', 'session', 'post_sse', 'persistent_history', 'abort_ui', 'mobile_layout'],
    }
    (OUTPUT / 'browser-agent-lab.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))
    browser.close()
