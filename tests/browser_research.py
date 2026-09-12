"""Explicit browser verification against a local deployment; synthetic tasks only."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUTPUT=Path(__file__).resolve().parents[1]/'harness/evidence/HA-0009'
OUTPUT.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':1440,'height':1150})
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.on('console',lambda message:errors.append(message.text) if message.type=='error' else None)
    page.goto(os.environ.get('HARNESS_TEST_URL','http://127.0.0.1:8765')+'/research')
    expect(page.locator('.demo-banner')).to_contain_text('不是 Claude SubAgent')
    page.locator('input[value=demo_b]').check()
    page.locator('input[value=demo_c]').check()
    page.get_by_role('button',name='创建并行演示').click()
    expect(page.locator('#root-status')).to_have_text('已完成',timeout=15000)
    expect(page.locator('.research-child')).to_have_count(9)
    expect(page.locator('#research-summary')).to_contain_text('9 个有效结果')
    with page.expect_download() as download:
        page.get_by_role('link',name='↓ research-report.md').click()
    assert download.value.suggested_filename=='research-report.md'
    previous=page.locator('#root-id').inner_text()
    page.get_by_role('button',name='重新运行',exact=True).click()
    expect(page.locator('#root-id')).not_to_have_text(previous)
    expect(page.locator('#root-status')).to_have_text('已完成')
    page.locator('#scenario').select_option('missing_risk')
    page.get_by_role('button',name='创建并行演示').click()
    expect(page.locator('#root-status')).to_have_text('完成 · 有资料缺口',timeout=15000)
    expect(page.locator('#research-summary')).to_contain_text('3 个失败/取消')
    expect(page.locator('#research-events')).to_contain_text('research.aggregated')
    page.screenshot(path=str(OUTPUT/'research-desktop.png'),full_page=True)
    page.reload()
    expect(page.locator('#root-status')).to_have_text('完成 · 有资料缺口')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Mobile overflow'
    page.screenshot(path=str(OUTPUT/'research-mobile.png'),full_page=True)
    assert not errors,errors
    report={'browser':browser.version,'errors':errors,'checks':['demo_label','nine_children','success',
            'artifact_download','rerun_new_tree','partial_failure','event_trace','reload','mobile_layout']}
    (OUTPUT/'browser.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    browser.close()
