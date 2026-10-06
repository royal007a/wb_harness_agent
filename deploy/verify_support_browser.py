"""Browser acceptance on an existing deployment; optional one synthetic real-model turn."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

def main():
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8765/support');p.add_argument('--out',required=True);p.add_argument('--chat',action='store_true')
    args=p.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as driver:
        browser=driver.chromium.launch();page=browser.new_page(viewport={'width':1280,'height':900})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        response=page.goto(args.url);assert response.status==200
        expect(page.locator('#runtime')).to_contain_text('已启用')
        if args.chat:
            page.locator('#chat-agent').select_option(label='HA0090 知识客服')
            page.locator('#new-session').click();expect(page.locator('#session-title')).to_contain_text('HA0090 知识客服')
            page.locator('#question').fill('合成商店未拆封商品几天内可以退货？')
            page.locator('#send').click();expect(page.locator('#send')).to_be_enabled(timeout=180000)
            expect(page.locator('#messages')).to_contain_text('未拆封')
            expect(page.locator('#messages summary')).to_contain_text('参考资料')
        else:
            expect(page.locator('#sessions button').first).to_be_visible()
            page.locator('#sessions button').first.click()
            expect(page.locator('#messages .message')).not_to_have_count(0)
        page.screenshot(path=str(out/'chat.png'),full_page=True)
        for title,name in [('Agent','agents'),('知识库','knowledge'),('工作流','workflows'),('MCP 与审批','mcp'),('模型与凭证','providers')]:
            page.get_by_role('button',name=title,exact=True).click()
            page.screenshot(path=str(out/(name+'.png')),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        for title in ['客服对话','Agent','知识库','工作流','MCP 与审批','模型与凭证']:
            page.get_by_role('button',name=title,exact=True).click()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),title
        page.screenshot(path=str(out/'mobile.png'),full_page=True)
        assert not errors,errors
        (out/'result.json').write_text(json.dumps({'url':args.url,'page_errors':errors,'mobile_width':390,'no_overflow':True,'real_chat_requested':args.chat,'panels':6},indent=2))
        browser.close()

if __name__=='__main__':main()
