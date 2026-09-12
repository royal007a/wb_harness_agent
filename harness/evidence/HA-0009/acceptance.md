# HA-0009 本地多专项编排验收

日期：2026-09-12。范围：ADR-0011 的离线本地切片；不是金融投研效果验收或原生 Claude SubAgent 验收。

## 结果

- 88 项测试通过，无失败或跳过；覆盖此前真实 Docker/Colima 与 Smolagents 脚本模型探针，以及本次持久父子 Run、1–3 并发、总预算、权限收窄、输入/产物归属、伪造结果拒绝、幂等、取消、部分失败与重启恢复。
- 研究页面 9 项、原工作台 12 项浏览器检查通过；无浏览器错误，桌面和 390px 页面已截图检查。
- 实际安装 claude-agent-sdk 0.2.152，构造 AgentDefinition/ClaudeAgentOptions 并检查字段；未调用 query/SDKClient、未启动 Claude CLI、未访问模型服务。
- API 健康、9 个子任务和下载产物 SHA-256 校验通过；manifest 保存源码哈希与 SDK 版本。
- 新页面 `http://127.0.0.1:8765/research` 已部署。现有 CSV 工作台回归通过，无数据库迁移；备份 `.local/backups/pre-ha0009-20260912.db` 保留。只监听本机，不开放远程服务。

## 可重复命令

```sh
HARNESS_DOCKER_TESTS=1 .venv/bin/python -m pytest -q --junitxml=harness/evidence/HA-0009/all-tests.xml
.venv/bin/python tests/browser_research.py
.venv/bin/python harness/research_evidence.py
.venv/bin/python -m pip check
node --check frontend/app.js
node --check frontend/research.js
git diff --check
```

原工作台浏览器证据位于 `baseline/browser.json`；浏览器会创建明确标为演示的任务。测试保留一项依赖弃用警告，不影响通过，仍需后续依赖升级处理。

## 边界与复核结论

已修正父级总配额校验与子执行 step_id 归属；子 Run 共用根 trace，但使用独立执行 step。已补充全局并发、排队树重启与部分失败覆盖。可信固定函数的取消是协作式的，不是任意代码的强制终止机制。

任务完成不等于数据充分：风险输出保持 not_assessed；没有联网新闻、真实财报、第三方 Skill、模型用量或实际投资结论。原生 Claude 接入仍受 HA-0008 与 TD-017/018/019 门禁约束。

回滚：回退本次代码提交并重启 `local.harnessagent.workbench`，保留当前兼容数据库；不得直接覆盖在线数据库或删除本轮后产生的数据。
