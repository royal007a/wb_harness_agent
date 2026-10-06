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
