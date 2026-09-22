# 工具与代码沙箱规范

## 工具分层

| 类型 | 适用 | 优点 | 约束 |
|---|---|---|---|
| Platform Tool | 权限、资源、产物等核心能力 | 统一治理、稳定契约 | 只能经 Tool Runtime 调用 |
| Adapter-local Tool | 单一 SDK 的短期探针或优化 | 接入简单、低延迟 | 不得承载核心业务规则 |
| MCP Tool | 跨项目或跨运行时复用 | 标准化、可独立部署 | 必须登记版本、来源和权限 |

P0 只提供三个 Platform Tool：

- `resource.inspect(resource_id)`：返回字段、类型、行数估计和受控读取句柄。
- `artifact.publish(relative_path, media_type)`：验证并登记 `/outputs` 内产物。
- `run.final_answer(summary, artifact_ids, metrics)`：提交待验证结果。

常规数据计算由 CodeAct 代码完成，不为每个统计函数创建工具。

## Tool Descriptor

每个工具必须声明：

- 稳定 ID、语义版本、提供者和内容摘要；
- 输入/输出 JSON Schema；
- `read | write | external_side_effect` 风险类别；
- 文件、网络、数据分类与密钥需求；
- 超时、幂等、重试和补偿语义；
- 可用环境和兼容协议版本。

模型可见描述不是授权。Tool Runtime 必须使用平台保存的 Descriptor 做最终判断。

## P0 沙箱配置

`codeact-data-analysis-v1` 的强制属性：

- 代码执行与控制面分离，使用一次性远程沙箱；
- `/inputs` 只读、`/outputs` 可写，其他宿主路径不可见；
- 默认无公网、无云元数据服务、无宿主 Docker socket；
- 非 root 用户、只读根文件系统、最小 Linux capability；
- CPU、内存、进程、磁盘、文件数、stdout 和墙钟时间均有限额；
- 依赖来自固定镜像和允许清单，禁止运行时安装；
- 不向沙箱注入模型、存储或外部服务长期密钥；
- 结束、取消或超时后强制清理，并记录清理结果。

具体数值由容量探针确定并版本化，API 请求只能在平台上限内进一步收紧。

用户创建 P0 Task 时一次性授权 `codeact-data-analysis-v1` Profile；授权只覆盖本 Run 的登记输入、固定镜像和 `/outputs`，不覆盖网络、宿主路径、依赖安装或外部写入。超出 Profile 的动作仍逐项拒绝或批准。机器可读 Draft 见 `specs/v1/policies/analysis-read-only.yaml`。

## 数据交换

- 输入资源在运行前完成格式、恶意内容和公式注入扫描。
- 大数据优先传资源引用或下推查询，避免整体进入模型上下文。
- 代码、参数、结果优先使用 JSON、安全文本和受控文件；默认禁止 pickle 等可执行反序列化。
- stdout/stderr 先截断和脱敏再进入事件；原始日志按敏感级别受控保存。
- HTML/SVG 产物作为主动内容处理，下载或预览前清洗脚本和外链。

## CodeAct 特有审计

至少记录：模型与提示版本、生成代码摘要、授权 imports、依赖镜像摘要、资源挂载、实际文件变更、网络拒绝、执行时间、峰值资源、退出码和产物摘要。

## 多 Agent 与沙箱

Child Run 默认获得独立沙箱。若复用父 Run 沙箱，必须显式声明共享状态、锁、数据范围和清理所有权；P0 禁止复用。

## 外部 Skill 隔离执行（ADR-0025）

外部 Skill 包与模型生成代码同样不可信。当前本地 `external-skill-stdlib-v1` 是一个更窄的、一次性 `manifest.json + entry.py` JSON transform 运行器：固定 image digest、`/skill` 与 `/inputs` 只读挂载、禁网、非 root、只读根、capability drop、无 Docker socket/宿主环境/凭证、资源限制和强制清理。它默认关闭，不能经宿主 Bash、SDK allowlist、MCP 或线程池绕过。

执行记录是独立 local-admin audit，不是 Product Task/Run Event；任何将其接入真实 Task、第三方资料、网络、依赖或副作用工具的提案必须先扩展 Tool Descriptor、审批绑定与 ADR。细节见 [外部 Skill 隔离运行时](EXTERNAL_SKILL_RUNTIME.md)。

## 安全判断

- 本地 AST 限制器是降低误操作的机制，不是强隔离边界。
- 容器也不是天然安全；必须配置内核、权限、网络、挂载和资源限制。
- 工具源码或 MCP Server 更新后，既有批准和能力令牌立即失效。
