# HA-0076 验证记录

2026-10-05；基线 `1fa03d35f39361d26445f5b81edd924cd784b8d1`。
这是综合吸收方案 A 的**事件隐私切片**，不是整个 A/B/C 完成。

## 实现

- Native/Pi 观察写库前均调用白名单投影，包含固定 kind、规范化 JSON 摘要和长度；SDK errors 只有条数及有界摘要，无正文预览。
- Native 原始 tool-use ID 只在内存用于关联；委派事件写 ID 摘要。Child 正文仍经现有引用检查发布到产物，Pi 候选仍由真实 Adapter 从内存解析，人工 Gate 保留。
- Pi stderr 设为 DEVNULL，EOF 和不可信协议 error code 只转换为固定错误。
- 未修改默认准入、凭据、Provider、沙箱或生产 DB。旧事件不迁移，不宣称擦除了历史正文；摘要与长度也不是匿名化。

## 已运行

1. 新文件 30 项；相关七文件共 **144 passed**，见 targeted.xml：
   `tests/test_runtime_event_metadata.py tests/test_claude_research_runtime.py tests/test_pi_contract_review_runtime.py tests/test_pi_contract_review_adapter.py tests/test_pi_sidecar.py tests/test_pi_product_http_contracts.py tests/test_workbench.py`。
2. `bash harness/verify.sh` exit 0，全仓 **1530 passed / 16 skipped**；其后状态/检索评测及前端语法检查均完成，见 verify.log。这些既有检索评测不新增检索质量声明。
3. 旧业务代码反例：独立 worktree 1fa03d3，只复制新测试、未被旧业务调用的 projection helper 和 Schema（为满足测试导入/初始化，不修改旧业务或 Adapter）。运行：
   `pytest -q tests/test_runtime_event_metadata.py -k 'native_persists or pi_real_adapter or stderr_not_read or untrusted_sidecar_error'`。
   **8 failed / 22 deselected / 0 errors**，均在事件中出现合成秘密、stderr PIPE 或错误文本未固定的行为断言处失败，见 before.xml；不将它表述为 8 个独立漏洞。临时 worktree 已清理。
4. 独立规范化测试向量：`{"text":"文","a":1}` 的 canonical ASCII JSON 长度为 23，SHA-256 `96c5811eff8ea4695744ac137570b1a46e8f664ce2ece28dd5b479e445670a78`，调用实际投影核对通过。
5. 测试源 SHA-256：`ffd13442f9befe113d0c3583e1e04761657e9145a4a6cdc39d7e358d566a087c`。

## 证据边界

Native 是合成 SDK 事件 + 临时 SQLite/TestClient；Pi 新测试用合成 sidecar 协议但运行真实 Adapter 提取及 Product 发布代码，相关既有测试另运行本机 Node Faux sidecar。stderr 的定向检查是 Popen 参数及 EOF 哨兵，不冒称真实恶意 CLI 的完整日志审计。未使用真实 Provider/CLI、生产输入、Keychain、OS 沙箱或网络出口隔离。

## 发布：阻塞，未部署

见 deployment-preflight.json。8765 connection refused；当前 managername=Background。gui/501 与 user/501 域现在均可读取（与旧证据不同），但本应用两域均未加载；批准发布器仍在任何变更前以 `gui_requires_aqua_caller` 拒绝，attempts=0。没有 bootstrap、bootout、后台替代进程或生产备份/迁移。

132 只读确认 systemd active，checkout 为 18406399318734cb7b8ab05581c1e84e81138337；未把该信息当作进程版本/健康验收。没有同步或重启132，遵守先本机后远端。

需要用户选择：在 Aqua 会话使用批准的 gui 发布路径，或者批准另行实现并测试 user/501 + Aqua/Background 拓扑。不能跳过这个前提直接发布公网。

## 后续

待独立 review；A 的环境白名单、受控 Native worker、独立 cwd/退出清理、auto memory，以及 B 的 tool-capable Provider/StreamFn/预算/审批桥和 C 的检索评测均未完成。保持默认关门；本任务不能标为部署验收完成。
