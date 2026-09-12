# HA-0007 本地验收

2026-09-12，macOS arm64 / Python 3.14 / Colima VM。

- `HARNESS_DOCKER_TESTS=1 .venv/bin/python -m pytest -q --junitxml=harness/evidence/HA-0007/all-tests.xml`：59 passed，两个既有依赖弃用警告。
- `.venv/bin/python harness/probe.py`：23 passed，真实 SDK/VM + 明示脚本模型，详见 probe.json。
- skill-creator `quick_validate.py skills/csv-group-analysis`：Skill is valid。
- `node --check frontend/app.js` 与 `git diff --check`：通过。
- `HARNESS_BROWSER_EVIDENCE=harness/evidence/HA-0007 .venv/bin/python tests/browser_smoke.py`：12 检查通过，console/page errors 为空。
- 桌面引擎页面已目视确认，Smolagents 显示待接入，固定分析可用；390px 浏览器无横向溢出。
- launchd `gui/501/local.harnessagent.workbench` 更新后 health=ok，model_calls_enabled=false；readiness 返回历史探针通过、真实路由关闭。
- 重启后可查询 4 条任务，最早创建时间为 2026-09-12T05:46:22.981316Z；浏览器验收创建了标记清楚的销售示例任务及重跑。
- 按本项目专属标签查询 Docker 容器为空，探针生成的容器已销毁；没有删除其他工作负载。

边界：不代表 Claude SDK 或真实模型已接入；没有进行联网金融抓取。脚本独立于 UI 的固定统计流程，无自动 Skill 发现或安装。模型接入与生产崩溃回收仍待验收。
