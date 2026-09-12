# 本地工作台模块

- 先阅读仓库根 AGENTS.md 与 docs/harness/LOCAL_WORKBENCH.md。
- 页面通过同源 API 获取真实任务、运行、事件与产物。
- 用户内容用 textContent 或 esc 转义，不执行报告或 CSV 中的 HTML。
- 异步详情请求必须验证当前选择代次，避免旧响应覆盖新 Run。
- 引擎与视觉接入状态必须真实显示；不伪造模型调用或运行成功。
- 控件需有可访问名称，兼容 390px 窄屏。
- 修改交互后运行 node --check frontend/app.js 与 tests/browser_smoke.py。
