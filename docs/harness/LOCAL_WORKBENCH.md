# 本地工作台 v0.1

2026-09-12 用户授权实现和本地部署。初版采用 [ADR-0009](../decisions/ADR-0009-local-workbench.md) 的本地边界。

## 使用

打开 http://127.0.0.1:8765，点击“使用示例销售数据”，再“创建并运行”。页面提供任务筛选、Run 选择、取消、重新运行、事件、权限快照及三个产物下载。也可以上传 UTF-8/GB18030 CSV，最多 2 MiB、20,000 行、100 列。

当前执行固定统计。提交前的本地 `intent-contract@1` 只用确定性规则识别 CSV 分析、校验目标与资源槽位，并在缺 CSV 时要求澄清；它不调用模型、不自动创建 Task、不自动选择其他引擎。准备就绪后仍由用户点击提交，目标原样作为 Task 意图保存。执行会计算行列数、缺失、不同值及数值列最小/最大/均值/合计，产出报告、完整率 SVG 和 analysis-manifest。模型调用和费用均为零。ADR-0018 在 `resource.inspect` 后保存一份固定统计 Checkpoint：仅当原 Run 随后失败或超时，工作台才显示“从检查点恢复”，创建同 Task 的新恢复 Run。Smolagents、Claude、Deep Agents、Pi、视觉和长期记忆是明确标记的后续能力。

## Local Agent Lab（ADR-0021）

入口为 http://127.0.0.1:8765/agent-lab。它是用户授权的本机准备切片：先创建无密 Provider Profile、Model Profile 和 Agent Profile，再创建会话并发送纯文本消息。后端把 user/local-demo 两条消息持久化，使用 POST SSE 返回 `delta` 与 `done`；前端用 `fetch` 和 `AbortController` 显示/停止流。

- Agent Lab 永远显示并返回 `model_calls=0`、`provider_calls=0`、`network_calls=0`、`tool_calls=0`；它没有任何真实模型回答能力。
- Provider Profile 只保存名称、类型、无凭证 Base URL 和启用状态；不会保存 Key/Token/credential reference，不测试健康或请求远端地址。
- Agent Profile 的工具绑定固定为 0。System Prompt、消息和 Session 都不能创建、修改或读取 Product Task/Run/Plan/Replan/Evidence/Checkpoint。
- 所有写入要求 `Idempotency-Key`；未知字段、凭证样式文本、外部 HTTP Base URL、禁用依赖和缺少 `Accept: text/event-stream` 的消息请求均拒绝。
- 数据保留沿用本机 SQLite 边界；仅限可信本机用户和非敏感演示内容。不要把密钥或高敏资料输入该页面。

HA-0007 增加 Adapter 生命周期、`GET /api/v1/readiness` 历史探针报告和引擎待接入状态。[VM/SDK 探针](ENGINE_PROBES.md)与[Skill CLI](SKILL_EXECUTION.md)可以单独运行；它们不自动启用产品模型执行，也不改变本页固定统计语义。

## Local Agent Runtime（ADR-0022）

入口为 http://127.0.0.1:8765/agent-runtime。它实现独立的 Provider、Model、Agent、Session/Message 和 Exchange 状态，及 `fetch` POST SSE 页面。与 Agent Lab 不同，它**没有**确定性 assistant 回复：默认环境将每个请求结束为 `MODEL_RUNTIME_DISABLED`，保留用户消息与 Exchange 失败状态但不伪造模型内容。

要允许一次真实 Provider 请求，进程必须显式以 `HARNESS_AGENT_RUNTIME=enabled` 启动，并且 Provider 是已实现协议、Profile 均启用、存在格式正确的 `keychain://harnessagent/<name>` 引用且 Keychain 在请求时可解析。该开关不是本地产品功能开关，也不构成数据外发授权；在实际启用前应另行完成数据范围、成本、超时、取消、健康与 L3 安全验证。现有部署不设置该条件。

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
- queued Run 重启后继续领取；running Run 明确失败 `SERVER_RESTARTED`。若它已有 ADR-0018 固定 Checkpoint，用户可创建受摘要绑定的新恢复 Run；否则仍只能创建普通新 Run。所有旧 Run 终态和产物保持不变；
- 本版使用固定工具函数，取消/超时为有界计算检查点的协作退出，未实现任意代码进程强杀或远程沙箱。

## API 范围

浏览器可读接口说明：http://127.0.0.1:8765/docs；机器描述：`/openapi.json`。

`POST /api/v1/tasks` 验证既有 `specs/v1/core-contracts.schema.json`；`POST /api/local/tasks` 是本地表单的显式简化入口，接受 `resource_id`、`objective`、可选 `timeout_seconds`，由服务端构造完整契约。未知字段/引擎/模型/能力拒绝。

`POST /api/local/intents:interpret` 是无状态预检入口，接受 `objective` 和可选 `resource_id`，返回版本化槽位、约束、固定路由、缺槽澄清或拒识；响应仅保留目标长度和摘要。它不创建 Task/Run。简化入口会在创建前重做相同预检，因此不支持目标无法绕过规则直接创建本地分析 Task。详见 [本地意图契约与规则路由](INTENT_ROUTING.md)。Agent Lab 的独立端点为 `/api/local/agent-lab/*`，其机器契约位于 `specs/v1/local-agent-lab.schema.json`；它不影响此处的分析意图路由。

事件采用 `GET /api/v1/runs/{id}/events?after=<sequence>` JSON 游标，最多 500 条/页。列表当前不分页，仅适合本地小规模使用。`/api/v1/tasks/{id}` 返回 `{task,runs}`，列表返回 `{items:[{task,latest_run}]}`；这是当前本地合同，完整目标接口仍见 [API.md](API.md)。`GET /api/local/runs/{id}/restore` 只显示固定 Checkpoint 是否可恢复；`POST /api/local/runs/{id}:restore` 需空 JSON 和幂等键，且只允许 failed/expired 的同 Task 固定统计恢复。另有 ADR-0019 的 Replan 控件：它只对真实 `ARTIFACT_PUBLICATION_FAILED` 显示固定候选，先 Try，再 Confirm 或 Cancel；调用方不能编辑计划。未实现 SSE、审批、可恢复模型 checkpoint、开放式动态 Replan 或多租户服务。

三个工具权限必须完整匹配：`resource.inspect`、`artifact.publish`、`run.final_answer`。有效权限始终拒绝 network/package_install/external_write/host_path/secret。预算 max_turns 限制三个固定工具步骤；无模型调用，因此 token/cost 实际消耗为 0。timeout 包含排队时间。队列最多 32 个活动 Run。

服务固定绑定 127.0.0.1，拒绝外部 Host、跨 Origin 和跨站请求，配置 CSP 与 nosniff。该措施用于本地原型边界，不等于生产身份认证或多租户隔离。生产使用需要单独完成 L3 门禁。

## 百度网盘 OAuth 连接

入口：http://127.0.0.1:8765/connectors/baidu-netdisk。它只实现官方 OAuth 连接，不会下载分享链接或读取文件。配置和用户操作见 [百度网盘连接器](BAIDU_NETDISK_CONNECTOR.md)。

在本机图形登录会话的交互式终端运行以下助手。它无回显读取 Client Secret，显式确认后才写入 Keychain；公开 App Key 通过 launchctl 注入当前登录会话并重启本地服务：

```sh
cd /Users/weberzhao/code/ai/harnessagent
.venv/bin/python harness/configure_baidu_netdisk.py
```

不要把 Client Secret、access token 或 refresh token 写进 plist、环境变量、终端历史或群聊；它们只能在本机 Keychain 服务 `HarnessAgent.BaiduNetdisk` 中存在。App Key 只在当前登录会话保留，重新登录后按需重新运行助手。为避免 OAuth 授权 code 出现在标准访问日志，前台启动与 launchd 均使用 `--no-access-log`。

## 验证

```sh
sh harness/verify.sh
.venv/bin/python -m pip install -r requirements-browser.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/browser_smoke.py
.venv/bin/python tests/browser_agent_lab.py
```

浏览器验收会在运行的本地服务中创建一条明确标记的示例任务，并保存桌面与移动截图。后端测试使用临时数据库，不修改本地演示数据。

证据：[HA-0006](../../harness/evidence/HA-0006/manifest.json)。尚未执行独立人工安全审查、生产压测或真实 Agent 沙箱测试。
