# 安全与数据规范

## 信任边界

外部模型、用户输入、上传文件、网页内容、MCP 服务、工具输出、适配器和第三方存储默认不可信。任何来自这些边界的指令都不能改变平台权限策略。

## 数据分级

| 级别 | 示例 | 默认规则 |
|---|---|---|
| Public | 公开资料 | 可在批准的服务间处理 |
| Internal | 配置、非公开运行元数据 | 工作空间内最小权限 |
| Confidential | 私有文档、业务数据 | 加密、受控模型和短期访问 |
| Restricted | 凭证、身份材料、高敏信息 | 默认拒绝进入模型与普通日志 |

每个资源必须记录分类、所有者、来源、用途、保留期和允许处理区域。

## 身份与隔离

- 服务端根据认证上下文确定工作空间，禁止相信请求体中的归属字段。
- 数据库查询、对象存储路径、缓存键、队列消息和日志均带隔离键。
- 服务账户按组件和环境分离，权限最小化并可轮换。
- 跨工作空间访问默认拒绝；支持能力必须单独建模和审计。

## 凭证

- 只保存密钥提供方的引用，不持久化或回显明文。
- Worker 按任务、工具、环境获取短期凭证。
- 凭证不得进入 Prompt、事件正文、产物、Evidence 或错误堆栈。
- 轮换、吊销、访问审计和泄漏处置必须可演练。

本地百度网盘 OAuth 连接器把 Client Secret、access token 和 refresh token 存入 macOS Keychain；SQLite 仅保留 state 摘要、期限和无密结果码。OAuth 回调 code 不进入应用事件或 access log；服务固定绑定 127.0.0.1，且只接受固定官方 HTTPS OAuth 端点。该本地边界不等同生产密钥系统或多租户授权服务。

ADR-0021 Local Agent Lab 不保存 API Key、Token、Cookie、`credential_ref` 或认证 JSON；它还拒绝明显凭证样式文本、URL 用户信息和外部 HTTP Base URL。Profile 的 Base URL 仅是未执行的配置字段，绝不能被误解为已完成连通性验证。Session/Message 只允许可信本机用户输入非敏感演示文本，使用纯文本渲染，不进入 Product Event/Evidence/Prompt 或真实模型上下文。

ADR-0022 Agent Runtime 只接受格式化的 `keychain://harnessagent/<name>` **引用**，不接受秘密值。SQLite、SSE、浏览器、错误信息和 Evidence 都不能包含 Keychain 内容；只有显式启用的传输边界才会解析引用。默认模型运行时关闭，Provider readiness 不进行网络请求。若部署到远程主机，必须在反向代理或应用层增加身份认证、TLS、最小访问范围及备份/保留策略后才允许输入非演示内容；本机单用户边界不能自动外推为公网授权。

ADR-0023 Research Agent Simulation 只读取项目自建的 synthetic 资源。Child Run 只获已分配资源的 `resource.inspect`，并核验 Skill 文件 SHA-256、资源摘要和 64 KiB 工具结果限制；它不加载第三方 Skill、脚本、MCP、Provider 或网络。报告中“未评估”只表示证据缺口，不是风险结论；真实金融资料、PDF、网页和模型输出进入前必须完成 TD-017/018/019/025/026 的独立准入。

ADR-0024 Native Claude Research 的默认门禁会在 `query()`、CLI、Keychain 和 HTTP 之前停止。允许启动时，模型 ID、费用上限、精确 HTTPS 域名、搜索/财务 endpoint、非秘密 Keychain 引用、Plugin SHA-256 和 Public PDF 资源摘要必须固定到 Task/Run；资料工具只返回有大小上限的 URI/摘要/时间/摘录，不能把原始网页、PDF、token 或任意宿主路径放入模型、Event、Artifact 或 Evidence。进程内 MCP 工具仍和工作台共进程，`dontAsk`、`allowed_tools`、Skill 过滤和网关校验不是 OS 隔离；TD-018 未关闭前不可加载第三方 Skill 或把此边界用于不可信资料。模型或 Child 没有来源 ID 时必须明确“未评估”，不能借缺失资料推出无 ST、无退市、无诉讼或任何投资结论。

## Prompt 与上下文安全

- 系统策略与外部内容使用结构化边界，不拼接为同等优先级文本。
- 检索内容中的“指令”只作为数据处理，不得修改工具权限。
- 在进入模型前执行数据分类、最小化和必要脱敏。
- 在进入工具前验证结构化参数，不从自然语言直接执行命令。
- 模型内部推理内容不作为授权依据，也不默认保存或展示。
- Plan、Evidence、Gap、Checkpoint 和 Replan 事件只能保存受控引用、摘要、分类、稳定错误码与必要的结构化状态；不得复制目标原文、Prompt、密钥或未脱敏工具结果。
- ADR-0018 的 SQLite Checkpoint 仅保存受版本约束的确定性统计状态及 Task/资源/适配器/权限/预算摘要；恢复前逐项校验，失败时不创建新 Run，且不以重算结果掩盖状态篡改。
- 模型化意图评测默认只使用手写的合成去标识夹具；影子候选输出不得带输入原文、Prompt、工具结果、凭证或生产标识，且不得影响用户请求。

## 工具与副作用

- 工具声明风险、输入输出 Schema、网络范围、文件范围和幂等能力。
- 默认拒绝未知工具、未知域名、动态代码和范围不明的写操作。
- 外部副作用等高风险动作必须展示目标、影响、参数摘要和可恢复性，逐项批准。P0 模型代码可由用户在 Task 创建时授权固定沙箱 Profile，不对每个代码 Step 重复弹窗。
- 批准令牌绑定任务、运行、工具版本、参数摘要、次数和有效期。
- Replan Confirm 还必须绑定候选计划、Checkpoint、输入资源、适配器/工具、有效权限与剩余预算摘要；这些任一变化会使 Try/Confirm 失效。
- ADR-0019 的本地入口只接受空对象：失败 Event、Evidence、Plan 和根因分类均由控制面从已持久化记录生成。它不得把错误详情、目标正文、Prompt、CSV 原文或调用方可控节点写入 Replan 对象；Try/Cancel 不执行适配器或创建 Run。
- ADR-0020 的 `gap@1` 仅保存失败 Event 关联、节点 ID、类型、严重度、受限可解决 Action 和状态；调用方不能创建或编辑它，且只有已绑定恢复 Run 的成功路径能够从 `open` 改为 `resolved`。
- 沙箱设置 CPU、内存、磁盘、时间、网络和进程限制。
- 模型生成代码只能进入一次性远程沙箱或经等价隔离验证的环境；本地解释器和 AST 过滤不构成安全边界。
- P0 沙箱默认禁网，输入只读、输出单独可写，不注入长期凭证，结束后必须销毁。
- ADR-0025 的外部 Skill ZIP 在登记时做严格文件名、大小、链接、UTF-8 manifest 和凭证样式检查；仅保存内容摘要和受控副本。执行前重算摘要，且在默认关闭门禁后才允许创建一次性禁网容器。Skill 不获得宿主路径、环境变量、Docker socket、网络、秘密、依赖安装或 shell。
- 外部 Skill 的独立本机 audit 仅保存版本/内容/输入输出摘要、profile/image 摘要、时长和清理状态；不保存第三方 stdout/stderr/堆栈，更不能伪装成有 Product `task_id`/`run_id` 的 Event。若接入 Product 运行，必须先使审计记录满足该关联不变量。
- ADR-0026 Memory Plane M1 只允许显式 Source Evidence + 原子 Fact 写入，拒绝凭证样式内容、Restricted 数据及 Public Bank 的 Internal Source。Memory 的来源正文不进入 Product Event、SSE 或 Evidence；Recall 仅返回 Fact 和 Source ID/ref/SHA-256，绝不返回原始正文。撤回/删除分别失效或物理移除可控正文/Fact，审计/tombstone 也不得保存正文。
- ADR-0027 M2-A 的 `recent_turns` 仅由调用方单次传入/返回，绝不进入 Memory 表、audit、Event、SSE 或 Evidence。Fact `detail` 必须是有界派生内容，若复制完整 Source 正文即拒绝；`:recall-details` 重新核验 Bank、来源状态和有效时间，且无效或跨 Bank ID 不返回正文。SQLite FTS5 仅是 canonical Fact 的可删除/重建投影，不能成为新的权威源或模型数据外发授权。
- ADR-0028 M3-A 的 Entity/Relation 只能由可信调用方以同 Bank 的 active support Fact 显式登记；服务不自动从 Source、聊天、文件或模型输出提取名称。图查询只接受 ID、至多两跳，并对 Node、Edge、support Fact、Source 状态和有效期逐层过滤；无路径不得宣称没有业务影响。Source retract/supersede 使依赖对象失效，delete 物理清理唯一支撑的 Entity/Relation 及关联边；Graph Bundle 只含 Fact statement 和 Source ID/ref/SHA-256，绝不含 Source 正文、模型输出、自动消歧结果或跨 Bank 名称。
- ADR-0029 M3-B 的 Entity Catalog 仅查同 Bank、active、Fact/Source/时间仍有效的已有 Entity，且只接受 casefold 精确 canonical name/alias。它不从模糊命中、别名相似度、模型或跨来源合并推断实体；多候选必须返回 `ambiguous`，调用方显式选取 ID。候选只给 support Fact statement 与 Source ID/ref/SHA-256，绝不返回 Source 正文；未命中、跨 Bank、失效、撤回或删除对象都只表现为空 `not_found`，不得泄露名称或存在性。
- ADR-0030 统一 M1/M2 Source-backed Fact 的历史可见性：读路径必须同时验证 Source 已发生、Fact 已发生、Fact validity window、active status、Bank 与来源保留期。未来记录被过滤只能表示“截至该时点不可读”，不得解释为事实不存在；FTS5 只是候选投影，绝不能绕过该规范过滤或导出原始 Source。
- ADR-0031 将 M2-B semantic/vector 设为版本化 fail-closed Gate：未记录语料 manifest、数据外发审查、删除/重建、离线相关性与延迟/成本基线时，状态只能是 `not_admitted`，没有 Provider、模型、网络、embedding 索引或记忆外发路径。即使将来状态被审查为 admitted，实际运行时仍需独立实现、最小化 Evidence、权限/预算和真实 L3 验证。
- ADR-0032 Fact Lineage 只由调用方提供已知 Fact ID，按同 Bank、Source active、Fact time/validity 再验证后有界回溯 supersede 历史。它把 superseded 节点显式标为历史，不能成为当前结论；retracted/deleted/跨 Bank/未来节点不返回，且不输出 Source 正文。
- ADR-0033 Team Coordination 拒绝凭证样式 collaboration metadata；Team Task、Handoff、Gate/closure 只保存受限目标、要求、范围、摘要、产物引用、SHA-256、审计理由和版本，不保存模型推理、Source 正文或工具输出。此本机 local-admin 切片尚无真实身份认证，`actor_id`/`reviewer_id` 只能作为协议字段，不得外推为用户或 Agent 授权；`scope` 也只是工作交接，不是工具允许列表。

## 高风险边界

以下动作默认需要人工批准或完全禁止：

- 对外发送、发布、付款、签署或修改远程系统；
- 删除、覆盖、批量更新或不可逆迁移；
- 在已批准 Profile 之外执行模型生成代码，或动态安装依赖；
- 把图片、扫描件或图表发送到尚未通过地域、保留和能力探针的视觉端点；
- 访问 Restricted 数据或扩大数据处理区域；
- 修改身份、权限、安全策略、密钥或审计记录。

## 数据生命周期

- 原始输入、Prompt、工具结果、产物、日志和备份分别配置保留期。
- 删除请求覆盖主存储、对象、索引、缓存和可控备份生命周期。
- 训练、评测和调试复用生产数据需要独立合法依据与显式授权。
- 导出使用加密、短期链接、访问审计和下载次数限制。

## 安全验证

- 威胁模型覆盖控制面、Worker、适配器、工具、MCP 和供应链。
- CI 检查依赖、密钥、许可证、Schema 和策略回归。
- 定期演练越权、提示注入、外部依赖劫持、凭证泄漏和数据恢复。
