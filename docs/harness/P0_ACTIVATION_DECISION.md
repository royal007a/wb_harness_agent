# P0 CodeAct 激活决策包

状态：待用户确认。本文把“本地工作台已经可用”与“P0 真实 CodeAct 已获准运行”分开；它不是模型、网络、生产或数据处理授权。

## 一页结论

当前 `0.1.0-local` 已具备可信的**确定性本地基线**：CSV 登记、不可变 Task/Run、事件、三类产物、数值回算、取消/恢复与受限 Replan 均有证据。它不能根据自然语言目标编写代码，因而不满足 ADR-0006 所定义的真实 CodeAct P0。

Smolagents `CodeAgent → 显式 SandboxExecutor → Colima VM` 已完成开发探针，但模型是预置脚本，真实模型路由仍关闭。下一步若获批准，只应启动一个**开发试点**：单 CSV、禁网、只读输入、无动态依赖、无外部写入、固定预算和独立结果验收；不构成生产上线。

## 事实与缺口

| P0 需求 | 当前证据 | 状态 | 进入真实试点前仍需 |
|---|---|---|---|
| 单 CSV、Task/Run、事件、受控下载 | `backend/service.py`、`backend/store.py`、工作台回归 | 已实现（本地基线） | 维持现有不可变 Task 与本地边界 |
| `report.md`、图表、`analysis-manifest.json`、数值回算 | `backend/analysis.py`、`tests/test_workbench.py` | 已实现（固定统计） | 用真实 CodeAgent 产物通过同一验收器 |
| 资源上限、UTF-8/GB18030、缺失值与注入文本防护 | `backend/analysis.py`、`test_encoding_mixed_missing_and_injection` | 已实现（固定统计） | 将等价输入约束落实到沙箱挂载和真实适配器 |
| 隔离代码执行 | `harness/evidence/HA-0007/probe.json` 与 `ENGINE_PROBES.md` | 开发探针通过 | 不把 Colima 历史探针当生产认证；补崩溃回收和真实适配器故障注入 |
| Smolagents CodeAgent Loop | HA-0007：真实 SDK + 脚本模型 + VM | 开发探针通过 | 使用本项目获准模型完成真实工具/代码/取消/Token/费用探针 |
| 模型端点、模型 ID、凭证引用、费用与数据范围 | `HA-0008` | 未提供 | 由用户提供本项目专用引用和上限；不得在聊天发送密钥或复用其他项目凭证 |
| P0 验收夹具 | `P0_DATA_ANALYSIS.md` 定义四类输入 | 部分覆盖 | 为真实适配器补齐正常时序、缺失/异常、非 UTF-8、恶意公式/提示文本四组可复现夹具 |
| 生产多租户、真实数据面、稳定 SLO | TD-010、TD-015、TD-016、TD-017 | 未开始 | 单独 ADR、身份/隔离评审、故障演练与运维门禁；不属于本次试点 |

## 请求确认的授权边界

要解除 HA-0008 的“开发试点”阻塞，确认记录必须同时给出以下内容：

1. **范围**：批准 ADR-0006 的“单个已登记 CSV → 受控 CodeAct → 报告/图表/清单”作为开发试点，而非生产发布。
2. **模型连接**：本项目允许使用的 endpoint、model ID、凭证的本地引用位置（环境变量名或 Keychain 服务名，不含明文）与最大测试费用/Token。
3. **数据范围**：首次探针只可使用 synthetic fixture，还是可使用用户明确批准的本地 CSV；两者都不得发往未批准的区域。
4. **沙箱条件**：继续使用现有禁网、只读 `/inputs`、只写受控 `/outputs`、无动态依赖、自动清理的配置；任何调整另行审批。
5. **停止条件**：认证失败、预算耗尽、网络/挂载/策略违反、取消不能清理、结果无法回算时立即停止，不回退到脚本模型或其他引擎。

## 批准后的最小执行顺序

1. 将用户的 endpoint / model ID / 凭证引用 / 预算写入本机受控配置，不写入仓库、SQLite、Event、Evidence 或聊天记录。
2. 仅用合成 CSV 做连接、最小代码、一次工具、超时取消和用量采集探针；记录无密证据。
3. 为 P0 四类夹具执行真实 CodeAgent，逐项验证禁网、挂载、产物、回算、错误码和清理。
4. 通过 L3 故障注入、人工审查和回滚演练后，才考虑将 `engine_smolagents_code` 从 blocked 改为受限可选。

## 不随批准发生的事

- 不开启联网、外部写入、动态依赖安装、任意 MCP、多 Agent 或自动跨引擎路由；
- 不把 Sandbox/SDK 试点升级为生产安全认证；
- 不开放通用 TAO、自由 Plan、LLM 根因判断或跨引擎 Replan；
- 不使用百度网盘、历史聊天、其他项目密钥或未明确批准的真实业务数据。

相关依据：[P0 范围](P0_DATA_ANALYSIS.md)、[引擎探针](ENGINE_PROBES.md)、[适配器契约](ADAPTER_CONTRACT.md)、[Plan/Replan 控制](PLAN_REPLAN_CONTROL.md)、[HA-0008](../../exec-plans/blocked/HA-0008-model-connection.md)。
