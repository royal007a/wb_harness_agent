# DSH 独立本地运行路径（HA-0077）

分支 `dsh/local-runtime-20261005`，目录 `/Users/weberzhao/code/ai/harnessagent-dsh`。
官方源码固定 `deepseek-ai/deepseek-harness@5badb15009ae1756c3afe0ae0cef1faafc290ccc`；运行依赖 `@deepseek-ai/dsh-sdk-client` 和 `@deepseek-ai/dsh` 固定 `0.2.1-alpha.1`（MIT），npm lockfile 固定传递依赖。没有复制或修改上游 Agent Loop。

## 调用链

浏览器 `/dsh` → 独立 Product Task/Run → Python 平台预算网关 → Node SDK bridge → 官方 DSH sdk-minimal Agent Loop。
DSH 的模型/工具请求回到短期认证的 loopback 网关；平台持有 Keychain 和 Provider 发送权，模型结果再映射为 DSH StreamChunk。
模型决定搜索/读取/继续/回答；平台独立决定输入范围、工具许可、预算、截止时间和发布。

1. 只支持公开/合成纯文本（最多20000字符）和问题（最多2000字符），不读取宿主文件。
2. 复用已审查的结构优先父子 Chunk helper；工具引用 `clause-N` 是本 Run 平台签发证据块编号，不是合同原始条号。
3. `search_document` 做字面子串检索，最多3个结果；`read_clause` 只读取已登记编号。无语义检索、外部搜索、shell、MCP、模型代码执行。
4. 每 Run 最多8次模型请求、16次工具执行、300秒；真实请求按完整模型容量保守预留，usage 不可靠即停止。没有自动重试、压缩或辅助模型请求。
5. DSH 观察事件只含哈希/大小；工具事件只含固定工具名、平台编号和参数摘要。最终正文只进入资源/产物，不进入观察事件。任务 objective 仍是用户输入，DSH 日志在自有临时目录。
6. DSH_HOME/HOME/cwd/TMPDIR 每 Run 独立，子进程环境明确允许集合。子进程没有 Provider 密钥，只有短期网关 capability。写入任何 prompt 前，先持久登记平台 mkdtemp 目录的名称、设备/inode 和进程组；结束时终止自有进程组、关闭网关后清理。重启读取自有 `.registry`，确认目录身份一致、租约释放且进程组不存在才删除。活进程、符号链接、损坏登记或身份变化保留待清理；不扫描未登记目录、不清理共享 home、不根据恢复的 PID 杀进程。硬崩溃到恢复完成之间可能存在短暂残留；遗留旧版本未登记目录不自动删除。
7. `integration_probe` 是明确的合成 Provider 自测，不是模型能力；`real_provider` 固定用户指定豆包 Coding URL/模型，未准入就409，不降级自测。
8. 发布要求实际读到至少一个证据块，且最终文本引用的 clause-N 均是本轮读到的块（至少一个引用）；空检索不算读到证据。这是引用关系检查，不是语义支持证明。succeeded 表示引擎完整执行并发布草稿，不代表人工复核或法律/投资结论正确。取消/失败不发布部分结果，终态不可覆盖；重启不恢复模型执行。

## 使用与部署

同一机器浏览器打开 `http://127.0.0.1:8876/dsh`。在其他机器直接用这个地址会访问那台机器本身；本次没有公网部署。
页面默认合成联调；消耗真实 Provider 配额必须显式切换。输入有权处理的文本，勾选公开/合成确认，创建 Run。页面显示持久状态、Token账本、工具执行记录、历史和下载。
主界面的默认 CSV 健康声明不是 DSH 就绪证据；以 `/api/local/dsh/runtime` 的启动提交、依赖、真实模式开关为准，并通过实际 Run 验证可调用性。

依赖安装：`cd dsh-adapter && npm ci --ignore-scripts --no-audit --no-fund`。本地服务复用主仓库现有 Python venv（只读依赖），代码、进程、DB、运行目录独立。Node 22.23.0。
配置模板 `deploy/dsh-local.macos.plist`：新 DB `.local/dsh.db`，只监听127.0.0.1:8876。user/501 bootstrap 能起服务，但本机该安全会话读取 Keychain 报 -25308，不作为可用的真实部署。`KEYCHAIN_PATH` 在当前 keyring 后端被忽略，不能解决问题。
实际启动命令 `.venv/bin/python deploy/start_dsh_session.py` 使用调用方已授权登录会话中的 launchctl submit，新 label `local.harnessagent.dsh-session`；检查干净提交、端口空闲和 Keychain 可读。它不修改 ACL，不把 Key 放入 argv/env/文件。会话退出、机器重启后的自动恢复没有保证；需要从同样获得授权的本机会话重新运行命令。不是把原8765的gui作业迁移或回滚。
Keychain 只存不透明引用，plist没有密钥。其他 Pi/Claude/native/外部Skill 门禁不变。原工作台入口可浏览，但 DSH 不自动继承它们的工具。未授权网关请求返回403，不改变合法Run的状态。

## HTTP 表面

- GET `/api/local/dsh/runtime`：静态能力与当前进程启动提交；不是 Provider 探活，不解析凭证。
- POST `/api/local/dsh/runs`：严格 request Schema + 1–128字符 Idempotency-Key，201历史创建收据。
- GET `/api/local/dsh/runs`、`/{run_id}`：列表/详情；模型正文不混入事件。
- GET `/api/local/dsh/runs/{run_id}/events?after=...`：继承500条分页、int64游标上限。
- POST `/api/local/dsh/runs/{run_id}/cancel`：空JSON对象；只取消当前Run，不覆盖终态。
- 产物使用既有 `/api/v1/artifacts/{id}/content`，正文以 text/plain 输出；前端只用 textContent。

请求和适配器输出的机器契约在 `specs/v1/dsh-runtime.schema.json`，Task/Run/Event/Artifact 继续使用核心契约。新HTTP响应的完整静态/动态OpenAPI闭环尚未补齐，不宣称全OpenAPI验收。

## 证据边界

这是单用户、loopback、本地进程集成，不是 OS 沙箱或多租户隔离验收。平台允许集合约束正常上游程序和模型工具，不证明恶意上游模块无法联网。只处理用户明确选定的输入；不发送真实合同/财务私密资料。
真实 Provider 的文档容量和套餐假设见 ADR-0077；不把订阅消耗当零成本，不保证取消后 Provider 停止计费。检索只做功能验证，没有质量对照评测；不能把此次工具回合当作 HA-0050 的评测修复。
历史 HA-0076 Pi evidence_ref 自由字符串旁路未在此分支假称修复；新 DSH 不使用那条 Pi 结果发布路径，事件只存平台编号/产物ID。
