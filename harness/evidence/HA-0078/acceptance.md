# HA-0078：DSH 补充验证

基线：c43df5b12f32e790dbb6994caa90556e508bea4c；分支 dsh/local-runtime-20261005。
环境：macOS，Python 3.14.7，Node 22.23.0，官方 DSH SDK/runtime 0.2.1-alpha.1。
范围：新增测试、规格、可重复突变脚本和证据；backend/adapters/frontend/dsh-adapter/deploy 没有改动。

## 结果

- 新增 `tests/test_dsh_adversarial.py` 60 项；与已有 `test_dsh_runtime.py` 30 项合跑：90 passed（dsh.xml）。
- SHA-256（新增测试）：b12f4f82f7b8cb4a00f1e4ae35582ac33c061e69d00e293f907a57ec47650f4a。
- 7 个定向突变均被行为断言拒绝，0 setup/collection errors（mutations.json 和各 mutation-*.xml）。不是全库 mutation score。
- 全量 `verify.sh` exit 0：1614 passed / 22 skipped，另含检索状态/Agentic 状态/Chunk 定向检查、既有评测、准入门禁、JS 语法和 diff 检查（verify.log）。22 skip 与基线口径一致，没有把 skip 当成通过。

## 分层证据

### 官方 SDK + 合成 Provider：11 项

真实启动官方 Node SDK/DSH，使用真实网关和两个工具；模型输出来自确定性合成函数。

- 8 次模型请求可成功；要求第 9 次时以 DSH_MODEL_CALL_LIMIT 停止，发送次数严格为 8。
- 16 次工具执行可成功；第 17 次以 DSH_TOOL_LIMIT 停止，已完成工具事件严格为 16。
- 负数、bool、小数、不一致 usage：一次请求后冻结 usage_unknown，保留预留、不发布、不重试。
- 同 Run 5 个 execute 调用只产生 2 次模型请求和 1 个产物；使用 Event 控制重叠窗口，不靠 sleep 猜时序。
- 搜索 → 读取 → 回答的三轮：下一次模型输入确实含上次工具返回的对应条款。
- 两个 Run 同时跑：产物各有自己的合成标记，没有另一个 Run 的标记；账本各自 2 次请求、事件无正文、临时目录清理。

### 平台编排/API：23 项

其中竞态、故障和工具入口通过合成 Adapter 精确控制，不宣称这些用例走过 SDK。

- 取消后 Adapter 仍返回有效结果：终态仍 cancelled，无产物。
- run.succeeded 写入时数据库触发器 ABORT：产物整体回滚，只留失败终态，不泄露错误正文。
- 第 2 次预留恰好足够与差 1 Token：分别发送 2 次/1 次，已知用量精确结算。
- 观察/结果信封多字段、摘要和 runtime 伪造拒绝；合成秘密不进事件。
- 实际发送前再次关闭真实模式：旧 key 回放拒绝且零写入，执行也不启动 SDK/读取凭据。
- 7 类非法工具/参数拒绝，无成功工具事件。
- 4 路并发同 key 只建 1 Run；剩余 1 队列名额被 2 路竞争时恰好 1 成功、1 RATE_LIMITED。
- 1001 条事件分页为 500/500/1/0，序号连续、空页游标稳定，读操作 total_changes 不变。
- 文档 20000/20001 字、问题 2000/2001 字、key 空/128/129 边界。

### Provider 协议：19 项

HTTPX MockTransport，没有真实网络或 Provider 调用。

- 200 正例以及 401/429/500/307 负例：固定 URL、max_tokens=2048、identity 编码、关闭环境代理和重定向；每条路径恰好 1 请求且关闭 1 次。
- gzip/identity/空 Content-Encoding 均在读正文前拒绝；256KiB+1 响应拒绝。
- 多 choice、finish_reason 冲突、重复/非法 ID、过多工具、非法/数组/超大参数、截断终止被拒。

### 目录所有权：7 项

- 名称越界、device/inode 错位、pgid 为 bool/1、版本错：全部保留而不误删。
- 锁未释放时 pending；释放后显式再次清理成功，再跑为空。它只证明显式重试可行，**没有实现后台自动重试**。
- 既有真实 SIGKILL → recover、符号链接、活进程等测试在上述 90 项中一起重跑。

## 可重复命令

```sh
.venv/bin/python -m pytest -q tests/test_dsh_adversarial.py tests/test_dsh_runtime.py --junitxml=harness/evidence/HA-0078/dsh.xml
.venv/bin/python -m harness.dsh_validation_mutations
env -u ARK_API_KEY -u OPENAI_API_KEY -u ANTHROPIC_API_KEY bash harness/verify.sh
```

突变脚本只在独立 Python 子进程内编译修改后的仓库模块，不改运行时代码文件；前后 SHA 一致。所有数据在 pytest 临时路径。新增测试 fixture 将凭据解析替换为失败哨兵，真实 HTTP 函数仅在 MockTransport 下调用。

## 发现与限制

- 首轮新增测试 49 通过、1 失败，原因是测试误用了事件字段 payload（实际为 data），修正后 60 新增/90 合计通过；没有借此修改生产代码。
- 突变报告首轮对 pytest 的 DID NOT RAISE 断言失败未分类，修正报告器并重跑全部 7 个突变；最终 XML 均可解析。
- 未发现需要在本轮修改生产代码的新缺陷；这不代表已穷尽所有边界。
- 未重新调用真实豆包、未重新跑浏览器、未验证法律/投研结论质量、吞吐、真实网络背压、多租户或 OS 沙箱。
- 不触碰正式数据库、Keychain、8876/8765/132 服务；原部署仍为 c43df5b。本次不需要部署测试代码。
- HA-0077 的 pending 清理无后台重试、DSH HTTP 响应 OpenAPI 未完整绑定、登录会话启动限制仍保留，不算本轮修复。
