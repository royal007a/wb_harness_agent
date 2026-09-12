# 本地工作台 v0.1

2026-09-12 用户授权实现和本地部署。初版采用 [ADR-0009](../decisions/ADR-0009-local-workbench.md) 的本地边界。

## 使用

打开 http://127.0.0.1:8765，点击“使用示例销售数据”，再“创建并运行”。页面提供任务筛选、Run 选择、取消、重新运行、事件、权限快照及三个产物下载。也可以上传 UTF-8/GB18030 CSV，最多 2 MiB、20,000 行、100 列。

当前执行固定统计，不解析自然语言意图；计算行列数、缺失、不同值及数值列最小/最大/均值/合计，产出报告、完整率 SVG 和 analysis-manifest。目标原样作为 Task 意图保存。模型调用和费用均为零。Smolagents、Claude、Deep Agents、Pi、视觉和长期记忆是明确标记的后续能力。

HA-0007 增加 Adapter 生命周期、`GET /api/v1/readiness` 历史探针报告和引擎待接入状态。[VM/SDK 探针](ENGINE_PROBES.md)与[Skill CLI](SKILL_EXECUTION.md)可以单独运行；它们不自动启用产品模型执行，也不改变本页固定统计语义。

## 启动和停止

```sh
cd /Users/weberzhao/code/ai/harnessagent
sh harness/init.sh
sh harness/start.sh
```

前台启动后用 Ctrl-C 停止。本机已提供 launchd 配置，后台部署方式：

```sh
mkdir -p .local
launchctl bootstrap "gui/$(id -u)" "$PWD/deploy/local.macos.plist"
launchctl print "gui/$(id -u)/local.harnessagent.workbench"
```

```sh
# 重启当前后台服务
launchctl kickstart -k "gui/$(id -u)/local.harnessagent.workbench"
# 停止并卸载当前登录会话中的服务
launchctl bootout "gui/$(id -u)/local.harnessagent.workbench"
```

plist 中路径为本机绝对路径，移动仓库需修改。当前注册属于登录会话，关闭终端不影响服务；重新登录后按 bootstrap 命令重新加载。不要同时启动前台和后台服务；数据库文件锁会拒绝第二个实例。

## 数据、备份和恢复

- `.local/harness.db`：SQLite WAL，保存资源原始字节、Task、Run、事件、产物和幂等记录；
- `.local/server.stdout.log` / `server.stderr.log`：launchd 日志；
- 本地文件没有应用层加密，使用可信本机账户和非敏感演示数据；
- 停止服务后，复制完整 `.local/` 到指定备份目录。恢复也在停止状态下进行，不在线覆盖数据库；
- queued Run 重启后继续领取；running Run 明确失败 `SERVER_RESTARTED`，用户可以创建新 Run；终态和产物保持不变；
- 本版使用固定工具函数，取消/超时为有界计算检查点的协作退出，未实现任意代码进程强杀或远程沙箱。

## API 范围

浏览器可读接口说明：http://127.0.0.1:8765/docs；机器描述：`/openapi.json`。

`POST /api/v1/tasks` 验证既有 `specs/v1/core-contracts.schema.json`；`POST /api/local/tasks` 是本地表单的显式简化入口，接受 `resource_id`、`objective`、可选 `timeout_seconds`，由服务端构造完整契约。未知字段/引擎/模型/能力拒绝。

事件采用 `GET /api/v1/runs/{id}/events?after=<sequence>` JSON 游标，最多 500 条/页。列表当前不分页，仅适合本地小规模使用。`/api/v1/tasks/{id}` 返回 `{task,runs}`，列表返回 `{items:[{task,latest_run}]}`；这是当前本地合同，完整目标接口仍见 [API.md](API.md)。未实现 SSE、审批、可恢复模型 checkpoint 或多租户服务。

三个工具权限必须完整匹配：`resource.inspect`、`artifact.publish`、`run.final_answer`。有效权限始终拒绝 network/package_install/external_write/host_path/secret。预算 max_turns 限制三个固定工具步骤；无模型调用，因此 token/cost 实际消耗为 0。timeout 包含排队时间。队列最多 32 个活动 Run。

服务固定绑定 127.0.0.1，拒绝外部 Host、跨 Origin 和跨站请求，配置 CSP 与 nosniff。该措施用于本地原型边界，不等于生产身份认证或多租户隔离。生产使用需要单独完成 L3 门禁。

## 验证

```sh
sh harness/verify.sh
.venv/bin/python -m pip install -r requirements-browser.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/browser_smoke.py
```

浏览器验收会在运行的本地服务中创建一条明确标记的示例任务，并保存桌面与移动截图。后端测试使用临时数据库，不修改本地演示数据。

证据：[HA-0006](../../harness/evidence/HA-0006/manifest.json)。尚未执行独立人工安全审查、生产压测或真实 Agent 沙箱测试。
