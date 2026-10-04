# HA-0075：预算基础组件作者验收记录

代码基线：1b9ae02。2026-10-04 作者运行，未获独立 Approved。

## 已实现

`backend/business_budget.py` 显式构造三张 SQLite 表，不接入现有 Service 启动。
根和多级子成员共享至多 20,000,000 Token；绑定摘要固定；BEGIN IMMEDIATE 预留；
重复 call_id 拒绝再发送；输入与输出 usage 对账，结算一次；未知用量、超额报告冻结根。
取消、重启后的独占恢复与异步调用包装器均已实现。包装器没有自动重试、工具执行、HTTP 或 Keychain。

`budgeted_model_call` 把共享预算检查真正包在合成异步模型回调之外，测试覆盖两个成员消费同一额度、
第三次调用不触发传输、重复请求不重发、预发送取消、在途取消、迟到响应及不响应取消的回调。
这里的合成工具调用只是返回数据，未执行工具、未运行 Pi Loop，不是真实业务集成。

## 验证

- `pytest -q tests/test_business_budget.py`：69 passed，见 targeted.xml。
- `pytest -q tests/test_business_budget.py tests/test_workbench.py tests/test_external_skills.py tests/test_external_skill_http_contracts.py`：199 passed / 5 skipped，见 related-final.xml；跳过的是已有真实隔离环境用例，不算通过。
- `sh harness/verify.sh`：exit 0。全量 1500 passed / 16 skipped；后续检索状态、Agentic 状态、Chunk、Memory/Team/Recovery 合成评测、两种准入检查、前端语法和 diff 检查通过。
- 任务登记 Draft202012 + FormatChecker、唯一 ID 和 diff 检查通过。
- 并发：16 线程共用 Store、4 个独立 Store/SQLite 连接分别验证不超额；没有启动多进程。
- 持久化：关闭连接再开库；恢复不会重置 spent 或把已发送调用退款。
- DB 插入触发器故障：预留不半写；去掉故障后同 call_id 能重新预留。

## 本轮发现并修正的验证问题

首次全仓是 1 failed / 1493 passed / 16 skipped（当时预算用例为 64 项），失败在旧
`test_registration_execution_replay_count_and_tamper`。其 `package()` 每次使用当前 ZIP 时间戳；
跨两秒生成的归档 bytes 不同，但测试误当作同一请求回放。独立时钟探针证实文件内容相同、归档不同。
新增 `test_package_fixture_bytes_do_not_depend_on_wall_clock` 在旧 helper 上行为失败，见 zip-fixture-before.xml。
只把 helper 的 ZipInfo 时间固定并保留 DEFLATED，业务幂等逻辑未改。最终全仓通过。

JUnit XML 仅做格式化、移除 hostname，并把超过 240 字的参数化测试名缩成函数名+原名 SHA-256；
不修改失败文本、结果或数量。verification.json 是作者执行摘要，不冒充原始全量 JUnit。

## not_evidence / 后续门槛

- 没有真实 HTTP、Provider、Keychain、真实 tokenizer、业务 PDF、投研资料或金额验收。
- 输入计数函数及 send 回调是可信平台依赖。本阶段不提供豆包安全输入上界、Provider 输出限额证明、隐藏重试控制或价格；不能声称 2000 万生产硬熔断已上线。
- 不响应取消的回调最多等待 0.1 秒清理，之后可能仍在后台运行；未知预留保留、根冻结、迟到结果不发布，不保证远端停止计费。
- 根的注册/子绑定/恢复由可信平台调用，还没有对接 Product Run 树、执行租约、根总时长、turn/工具预算及 Handoff/Gate。
- 未修改运行中的服务或正式 DB，不改变 Pi/Claude/Chat 准入；8765/132 未部署此尚未被服务引用的组件。
- 不能把本任务完成度算成真实合同审查或真实投研已可用；下一阶段仍需真实 transport 和业务适配器，集成发布遵守先8765再132。
