# Provider、Agent、Skill 与对话引擎六篇阅读总结

状态：已阅读，作为本地 Agent Lab 准备切片的设计输入；不是对课程示例架构或实现细节的照抄授权。

## 来源与范围

2026-09-13 阅读的本地 PDF（均为用户提供的个人学习材料）：

| 篇 | 文件 SHA-256 | 主题 | 对 HarnessAgent 的可采纳结论 |
|---|---|---|---|
| 13 | `ae6489a82c5413c6189131dcabd824140c000dba25300884dfcd70a222b91eb4` | 模型提供商管理 | Provider、模型与健康状态要分层；适配器隔离协议差异。 |
| 14 | `679422cc2f79d0f69710418f26514f02c8914437d9626e361210ed3109721ce7` | Skill | 将稳定 SOP、产物和验证方式沉淀为按需加载的经验，而不是替代权限。 |
| 15 | `8ad980df6f4c228e988acec3d073f3865d32b7d4aef94bfcf4f8810e98561522` | Agent 创建与配置 | Agent 是版本化的配置模板；身份、能力绑定与运行参数必须分开。 |
| 16 | `97c844045504bc7ba585f271b146b0bb61a340001cefa2ffc7e1eb435bc5bc13` | 对话引擎（上） | 会话、上下文、消息持久化和 SSE 是后端处理链路，不能由前端直连模型替代。 |
| 17 | `308566bfae967862555938f7eebc353270561585723e1eedee1bd09febd71625` | 对话引擎（下） | 历史记录、热上下文和检索知识应分层；先采用有限滑动窗口，避免把聊天记录误当 RAG。 |
| 18 | `3eb32927bb04323cd034ba1c84e7a85f6199d4b44c28584c615bfb18cbcff5fc` | 流式聊天前端 | 复杂交互按结构→行为→细节交付；POST SSE 必须用 `fetch` 读取流。 |

所有 PDF 已进行文本抽取并抽查关键版面（Provider 表/适配器、Agent CRUD、SSE 链路、上下文流程、流式前端时间线）。本文只记录综合判断，不复制课程原文。

## 六篇共同的方法论

1. **先建立领域模型，再开始 CRUD。** 用“是什么、在哪里用、由什么组成、架构怎样”四问减少误建模。课程中 Provider、Agent 和对话引擎都沿用这条路径。
2. **配置、执行和状态不可混淆。** Provider/Model/Agent 是配置；会话与消息是用户数据；执行状态、权限、Evidence、Checkpoint 与 Replan 是控制面状态。后者不能被一段 Prompt 或一个页面表单绕开。
3. **固定流程写成 Skill，而不是写成更多工具。** Skill 应给出输入、步骤、产物、验证和人工决策点；工具只保留独立、可复用、具有明确输入输出契约的能力。
4. **适配器消化供应商差异。** API 格式、认证头和 SSE 解码留在 Provider Adapter；核心服务只接收统一请求/响应。新增类型应以注册扩展，而不是在业务层扩张 `if/else`。
5. **对话不是简单转发。** 后端要负责 Session 归属、受限上下文组装、用户/助手消息持久化、流式生命周期、取消和异常语义。模型无固有跨请求记忆。
6. **流式 UI 是时间线。** 发送后立即出现用户消息与占位助手消息；逐个处理 `delta`；`done` 收束 UI；错误或取消恢复输入。POST 响应流应使用 `fetch`，不能把 `EventSource` 当作 POST 客户端。

## 对当前 HarnessAgent 的判断

当前系统的核心不是教学项目中的“智能客服平台”，而是厂商中立的 Agent 工程控制面。它已经有 `Task → Run → Event/Evidence → Checkpoint → Replan` 的受限、确定性路径，且 P0 未批准模型调用。因此不能直接采用下列课程做法：

- 不能把 API Key、Token 或 `auth_config` 明文写入 SQLite、前端、事件或 Evidence；本项目的规则只允许凭证引用，当前本地演示连引用也不消费。
- 不能把 Provider 健康检查、模型枚举或聊天配置变成后台联网探测；这会绕开外部副作用授权和 TD-016/017。
- 不能把 Agent 配置页宣称为 ReAct、SubAgent、持久记忆或真实 Claude SDK 路由。
- 不能让聊天输入改变 Task 权限、Plan、Checkpoint、Evidence 或 Replan；它们属于独立控制面。

## 可执行设计映射

| 课程概念 | 本轮本地切片 | 明确边界 |
|---|---|---|
| Provider / Model | 无密 Provider Profile 与 Model Profile 配置记录 | 不保存凭证、不测试网络、不枚举远端模型。 |
| Agent | `identity + model_profile_id + system_prompt + typed limits` | 工具绑定固定为空；不执行 Function Calling 或多步循环。 |
| Session / Message | SQLite 中独立会话、消息、幂等 exchange | 与 Product `Task/Run`、任务事件和长期记忆隔离。 |
| SSE | `POST` 返回 `delta/done/error` 事件 | 内容来自显式标记的本地确定性演示器，不调用模型。 |
| Context | 读取最近的受限消息数供可观测性显示 | 不把用户数据拼装至模型，也不启用 Redis/RAG/摘要压缩。 |
| Skill | 本轮实现步骤与验证矩阵写入执行计划 | Skill 不授予 Provider、网络或工具权限。 |

## 后续真实接入的门禁

真实 Provider Adapter 或 Claude SDK 对话路由只能在单独 ADR 和 L3 证据后开放：端点/版本/能力探针、密钥引用和轮换、数据分类与地域、预算、超时与取消、SSE 异常、审计、模型输出治理、沙箱与 Tool 权限，以及真实恢复/回滚演练。当前对应 TD-016、TD-017、TD-022、TD-023 仍未关闭。
