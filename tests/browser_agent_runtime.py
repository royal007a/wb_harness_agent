"""Browser acceptance for ADR-0022 against a separately started local deployment."""
import json
import os
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(os.environ.get('HARNESS_AGENT_RUNTIME_BROWSER_EVIDENCE', ROOT / 'harness/evidence/HA-0025'))
OUTPUT.mkdir(parents=True, exist_ok=True)
suffix = str(int(time.time() * 1000))
with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    base_url = os.environ.get('HARNESS_TEST_URL', 'http://127.0.0.1:8765')
    credentials = None
    if os.environ.get('HARNESS_HTTP_USER') and os.environ.get('HARNESS_HTTP_PASSWORD'):
        credentials = {'username': os.environ['HARNESS_HTTP_USER'], 'password': os.environ['HARNESS_HTTP_PASSWORD']}
    context = browser.new_context(viewport={'width': 1440, 'height': 1050}, device_scale_factor=1,
                                  ignore_https_errors=base_url.startswith('https://'), http_credentials=credentials)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
    page.goto(base_url + '/agent-runtime')
    expect(page.locator('#runtime')).to_contain_text('默认关闭外部模型调用')
    page.locator('#provider-form input[name=name]').fill('Runtime Provider ' + suffix)
    page.locator('#provider-form input[name=base_url]').fill('https://example.invalid')
    page.get_by_role('button', name='保存 Provider').click()
    expect(page.locator('#provider-list')).to_contain_text('blocked_by_runtime_gate')
    page.locator('#model-provider').select_option(index=1)
    page.locator('#model-form input[name=display_name]').fill('Runtime Model ' + suffix)
    page.locator('#model-form input[name=model_id]').fill('runtime-model-' + suffix)
    page.get_by_role('button', name='保存 Model').click()
    expect(page.locator('#model-list')).to_contain_text('Runtime Model ' + suffix)
    page.locator('#agent-model').select_option(index=1)
    page.locator('#agent-form input[name=name]').fill('Runtime Agent ' + suffix)
    page.locator('#agent-form textarea[name=description]').fill('浏览器运行时验证。')
    page.get_by_role('button', name='保存 Agent').click()
    expect(page.locator('#agent-list')).to_contain_text('Runtime Agent ' + suffix)
    page.locator('#session-agent').select_option(label='Runtime Agent ' + suffix)
    page.get_by_role('button', name='新建会话').click()
    expect(page.locator('#chat-form')).to_be_visible()
    page.locator('#chat-input').fill('不应生成演示回答。')
    page.get_by_role('button', name='发送').click()
    expect(page.locator('.bubble.assistant').last).to_contain_text('MODEL_RUNTIME_DISABLED', timeout=10000)
    page.screenshot(path=str(OUTPUT / 'agent-runtime-desktop.png'), full_page=True)
    page.reload()
    expect(page.locator('#session-list')).to_contain_text('Runtime Agent ' + suffix)
    page.set_viewport_size({'width': 390, 'height': 844})
    expect(page.locator('#new-session')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow'
    page.screenshot(path=str(OUTPUT / 'agent-runtime-mobile.png'), full_page=True)
    assert not errors, errors
    report = {
        'browser': browser.version,
        'errors': errors,
        'checks': ['default_runtime_gate', 'provider_readiness_zero_network', 'profile_chain', 'session', 'post_sse_error', 'no_synthetic_answer', 'persistent_exchange', 'mobile_layout'],
    }
    (OUTPUT / 'browser-agent-runtime.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))
    context.close()
    browser.close()
