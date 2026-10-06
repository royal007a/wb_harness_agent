# HA-0090 进行中证据

编号说明：初始提交 dfa106a 使用 HA-0080；因并行 DSH 发布已占用该号，客服任务
统一迁至 HA-0090，不覆盖 DSH 证据。旧提交历史保留。

## Provider 原子切片

- `pytest -q tests/test_support_providers.py`：18 passed。
- `pytest -q tests/test_support_providers.py tests/test_workbench.py tests/test_agent_runtime.py`：78 passed。
- 覆盖：AES-GCM 密文与 provider AAD、轮换、无密返回、主密钥缺失/坏权限/符号链接、
  输入/端点拒绝、MockTransport 探测协议、每日限额、鉴权错误脱敏、后台自行发起且
  due 时间阻止重复、取消与编辑互斥、HTTP 明文代理禁止上传凭证。
- 模型/网络均为合成 MockTransport；未读取 Keychain，未部署。
- 本证据不证明课程平台已完成；Agent/流式会话、知识库、工作流、MCP、浏览器、
  真实 Provider、双端发布仍未完成。

## 会话原子切片

- `test_support_chat.py` + Provider + workbench + agent_runtime：93 passed（chat.xml）。
- 真 SSE 解析经 MockTransport 验证：delta、工具参数分片、stop/tools 终态与 usage/DONE。
  缺 usage、EOF、length、停止后继续内容均不发布，账本未知用量冻结；重放不再发请求。
- Agent 配置快照、多轮历史、每次消息独立共享账本、工具权限/Schema/最大轮次、
  断线和工具等待中取消、重启恢复、原子 assistant 提交、终态不被取消覆盖。
- `/support` 页面及原生 JS 已实现，语法检查通过；**尚未浏览器验收**。
- 预算目前为 Ark 模型保守预留完整 1,024,000 输入上限，不将字符估计冒充硬预算。
  小于此预留的消息预算会在发送前拒绝；实际 usage 结算后释放差额。
- 知识库、工作流、MCP、真实 Provider、双部署仍未完成。

## 知识库原子切片

- Provider + Chat + Knowledge：48 passed / 1 skipped（knowledge.xml）。跳过项是需要显式模型目录的真实 BGE 探针。
- 显式配置模型后单跑该探针：1 passed（knowledge-real-embedding.xml）；真实本地 ONNX
  语义向量将“买的东西不想要了，可以退回去吗？”在三个独立候选中排到退货条款。
  此单例只证明真实向量链路，不是检索质量评测，更不是真实豆包回答评测。
- Chromium + 随机回环端口 + 临时库：1 passed（support-ui.xml）。页面实际创建库、
  上传、索引、检索、绑定 Agent、流式回答、来源展示、刷新历史、390px无横向溢出。
  该浏览器测试的模型和向量均为明确的合成适配器，外发0次。
- 反例覆盖：跨库隔离、删除失效、回答发布前删除/停用重查、坏向量、嵌入/第二块写入
  失败时无半份索引、取消工作进程、重启遗留处理状态、上传/检索上限。
- FastEmbed 0.8.1，模型 BAAI/bge-small-zh-v1.5（512维），Qdrant ONNX 修订
  `46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59`。部署时显式下载6文件并记录SHA，
  运行时只读本地文件、校验摘要、offline环境，不自动下载。依赖来源：
  https://qdrant.github.io/fastembed/examples/Supported_Models/
- 工程取舍：SQLite精确余弦适用≤4000块的小库；不是pgvector/ANN。TXT/MD已实现；
  PDF/OCR不在此原子切片。课程知识库的异步管线、状态、删除、绑定与聊天注入已落地。
- 仍未完成：工作流、MCP、完整机器HTTP合同、真实对话与自动探测部署验证、8765/132发布。

## 工作流原子切片

- Workflow + Chat + Knowledge + Chromium：53 passed / 1 skipped（workflows.xml）。
  工作流定向新增22例，覆盖线性、true/false分支、坏边/环/孤点/未知节点、变量单次替换、
  配置冻结/漂移、知识库权限、工具权限、节点异常、发布事务失败、第二次模型调用预算
  不足、取消关闭上游和节点终态、重启恢复、幂等重放不重新发请求。
- 模型节点复用同一个 BusinessTokenLedger/root/binding；无独立私账，无隐式重试。
  中间输出只在内存变量池，节点记录持久化状态/耗时/摘要；END输出和run成功与assistant原子提交。
- Chromium 实际从 JSON 编辑器创建分支工作流、更新 Agent 绑定、新建会话执行，
  点击执行记录查看成功状态。手机宽度曾发现PRE溢出（内联样式被CSP拒绝），已用独立CSS修复。
- 课程 API_CALL 不开放任意URL，映射为受Agent权限控制的 TOOL；图静态拒环，并有32步上限。
  当前JSON编辑器不是可视化拖拽画布。模型节点中间阶段只推状态，不把分类文本冒充最终回答。
- 本轮仍无真实Provider、无生产部署；MCP及部署验收继续进行。
# MCP 切片追加

- 官方 MCP2.2.0 Streamable HTTP 服务和客户端在回环HTTP上完成发现/资格/申请/查询/取消。
- 写操作只生成待确认动作；平台确认、版本/会话重查后执行，未知结果不重试。
- 测试 `support-suite.xml`：78 passed / 1 skipped（本地真实向量另有已通过证据）。
- `mcp.xml`：MCP、聊天、浏览器23 passed；包括390px完整发现→调试→人工确认→SQLite记录。
- 内置退款都是合成记录，无支付系统、无真实资金动作。
- 132依赖预装使用独立环境；其默认PyPI镜像缺cryptography50，改官方PyPI后继续，未改旧运行环境。
- 仍未作为部署、真实Provider、生产多租户验收；正在做双部署。
- `sh harness/verify.sh` 独立运行 exit 0：1602 passed / 23 skipped；其后评测、接口清单和静态检查也通过（verify.log）。这是本分支基线和依赖条件下的数量，不与 DSH 分支1686直接比较。

## 真实调用发现与修复

- Ark 在 finish choice 和其后空 choices 帧重复相同 usage，旧解析器安全拒绝。
  精确兼容后，同值只结算一次；冲突、提前、三次和重复空帧反例均拒绝（ark-stream.xml）。
- 首次真实工作流触发 usage breach：预留输出2048，报告输出2291（含推理），没有发布。
  不能提高预算掩盖发送参数问题：改用总输出 max_completion_tokens，并显式关闭 thinking。
  [官方参数说明](https://docs.volcengine.com/docs/LakeAIService/DeepThinkingDoubao-15-thinking-pro?lang=zh)
  区分回答上限与含推理的总输出上限；本平台仍以实际usage校验，不把参数当供应商必然守约证明。
- 修复后 `local-live-final.json`：真实聊天、BGE索引与RAG、LLM工作流、官方MCP发现、
  真实模型查询并申请合成退款、人工确认、重复确认不再执行全部通过。
- 浏览器真实调用后发现多会话列表撑开手机网格，补 min-width:0/minmax(0,1fr)，
  新增17会话反例通过；部署页面六模块390px无溢出、无JS错误（local-browser）。

## 最终验收（2026-10-06；以上未完成字样是阶段历史）

运行版本：`7eaf317817fe02c754842f0c13a32e53519c7007`。分支
`feat/customer-support-20261006`；后续收尾提交只改状态、文档与证据。

| 合同 | 可复核证据 |
| --- | --- |
| 1 Provider CRUD、加密凭证 | providers.xml、local-storage.json、remote-restart-storage.json；实际Key仅密文入库，master0600，DB/WAL/进程argv/env/最近200行journal无明文 |
| 2 自动联网 | local-periodic-probe.json：启动和900秒到期两次真实探测；remote-live.json自动探测；日计数与due跨重启保存 |
| 3 Agent能力配置 | support-suite.xml、两端live.json；Server/工具/知识库/工作流显式绑定，配置冻结/停用反例 |
| 4 持久流式对话 | chat/ark-stream测试；两端真实SSE、用量、重放不新增调用，local-restart及remote-restart-storage；失败/取消离线反例 |
| 5 真实向量RAG | 两端real_embedding与real_rag_chat：本地BGE512维、ready索引、来源引用；knowledge测试删除/失效/回滚 |
| 6 工作流 | workflows.xml；两端真实LLM节点和END发布，节点记录；条件分支/预算/取消/变量/坏图反例 |
| 7 MCP | 官方2.2.0真实HTTP发现四工具，豆包资格查询→申请待确认→人工确认→SQLite合成退款；重复确认无第二次写入 |
| 8 UI | local-browser-final与remote-browser截图；六模块、390px、无JS错误/溢出；legacy-browser旧工作台回归 |
| 9 双端发布 | remote-deployment.json、local-restart.json、remote-restart-storage.json、remote-browser/result.json；未认证401、认证200、HTTP Key写入403、MCP无能力令牌403 |

验证计数：`verify-release.log` exit0，**1607 passed / 23 skipped**；真实Embedding显式运行
及Linux客服测试已补充，`linux-tests.log` **82 passed / 1 skipped**（Linux未装浏览器）。
浏览器在本机Chromium访问本机及公网真实nginx，不将未认证401冒充代理验收。
远端stage的1414个已跟踪文件逐一SHA256核对。公网验证临时Basic用户已删除，原harness登录未改。

成功的主要真实模型验收（不包括前面的失败诊断、浏览器额外对话和定时探测）：
本机4个业务会话共6次模型调用，4911 Token；远端见 remote-live.json 中每个Exchange账本。
失败历史保留：首次重复usage被拒；一次旧max_tokens导致2291输出超过2048预留被账本拒绝；
两次均没有发布assistant。修复后并未修改这些失败记录来充当成功。

部署地址：本机 http://127.0.0.1:8765/support ，公网 http://118.196.123.132/harness/support 。
本机launchd label `local.harnessagent.support-session` 只在当前登录会话，机器重启需再启动；
132沿用systemd `harnessagent`，DB `/var/lib/harnessagent/harness.db`，仅回环8765监听。
发布前备份 `/var/backups/harnessagent/ha0090-20261006T082856Z`，内含旧应用、实际SQLite及发布回执。
旧 `.venv` 保留，新环境 `/opt/harnessagent-support-env`；未改其他服务或DSH8876。
失败恢复旧应用/配置不代表DB回滚。需要恢复时先停harnessagent，核对备份归属，恢复application.tar.gz
并还原此前support.conf（此前不存在则移除本次drop-in），daemon-reload再启动；附加表不自动删除。
主密钥须单独备份，不能丢失后自动重建；不要把主密钥或原始凭据放入Git/Evidence。

边界与遗留：

- 仅单管理员公开/合成资料；无多租户、独立安全review、生产压测、任意HTTP/代码节点、PDF/OCR、ANN规模或真实资金通道。JSON编辑器不是拖拽画布。
- 真实模型在一份退款解释中把 `amount_minor=19900` 错写成“¥19900.00”，实际合成退款记录仍为19900分。
  当前权限、参数与审批控制不能证明回答语义正确；金额/业务结论须对照原始工具记录人工核对，不将成功状态当正确率。
- 全部回答按文本呈现，不执行模型HTML；Markdown符号可能原样显示。
- 远端HTTP没有TLS：Key写入被拒；仍不应在该公网入口提交敏感会话。建议使用SSH隧道或另行配置HTTPS。
- 132在清理本次旧stage和下载wheel缓存后仍仅约820MiB空闲（98%使用）。删除的247212341字节均为本次可重建缓存，正式数据/当前release/备份保留；需另行容量治理。
- 新支持接口已有运行时严格输入与行为测试，但没有宣称补齐全站静态/动态OpenAPI。
- 本次未独立复审，不借用DSH的Approved为客服平台背书。
