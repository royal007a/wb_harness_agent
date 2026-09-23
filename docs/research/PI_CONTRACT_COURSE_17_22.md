# Pi 合同审查课程 17–22：阅读结论与落地映射

## 资料清单

本次阅读范围是 `/Users/weberzhao/Downloads/Harness Agent 脚手架实战课` 中的 17–22 六份 PDF，共 50 页。每份资料的文件名与 SHA256 以 `evidence/course-17-22-manifest.json` 固化；课程只作为设计参考，不代表本项目已具备对应外部运行能力。

## 关键设计结论

1. Pi 分层为 `pi-ai`（Provider/Model 抽象）、`pi-agent-core`（事件驱动 Agent Loop）、`pi-coding-agent`（Session、压缩、工具和扩展）、`pi-tui`（差分渲染 UI）。
2. 文档处理应拆成解析、分类、分块、审查和聚合；业务规则放在 Skill，运行时负责事件、工具和状态。
3. 长合同不能把全文直接塞入上下文：按章节/条款分块，逐块产出结构化风险，再做全局交叉检查和汇总。
4. 安全护栏应在模型外部拦截工具调用、工具结果、上下文和 Provider 请求；敏感信息、域名、路径、危险命令和费用都必须可审计。
5. ChatPanel 使用事件流驱动 UI；上传、权限、工具确认和会话隔离不能由前端单独决定。TUI 与 Web 共享事件语义，不共享渲染实现。

## 已落地的第一条纵切片

`POST /api/local/pi-contract-pipeline/preview` 实现课程 16–18 的无模型预览；
`POST /api/local/pi-contract-pipeline/review` 接入课程 19 的确定性 Skill 基线；`review-stream` 接入课程 21 的事件流适配：

- 仅接受已登记 `Public` PDF；解析使用 `pypdf`，输出不包含原文正文。
- 生成确定性合同类型、关注点、章节/条款 chunk 摘要和 SHA256。
- 扫描身份证号、手机号、银行卡号、邮箱；命中时返回 `needs_human`，只返回类型与数量，不泄漏原值。
- 响应通过 `specs/v1/pi-contract-pipeline.schema.json` 校验；幂等键保证重放一致。
- `external_calls=0`、`model_calls=0` 是契约字段，不能把该切片描述为真实 Pi 或外部模型运行。
- review 端点从服务端重新构建预览，不接受调用方伪造的 chunk；输出始终是 `needs_human`，并为每个 chunk 生成 `evidence://` 引用。
- review-stream 只发送结构化 preview/finding/done 事件，不发送合同原文；仍然是确定性、无模型、无网络的 ChatPanel 数据源。

## 非目标与后续顺序

本切片不实现真实 Provider、联网 WebSearch/WebFetch、法律结论、Pi Node sidecar、ChatPanel 或 TUI。后续按以下顺序推进：

1. 将 chunk 结果接入 `contract-risk-review` Skill，并增加跨 chunk 风险聚合与人工 Gate。
2. 把课程 20 的护栏抽成独立事件拦截器，覆盖工具调用、路径、域名、费用和取消。
3. `review-stream` 已完成事件 SSE 适配；最后再做 TUI 事件渲染。
4. 只有模型/Provider 准入契约、费用上限、端点白名单、Keychain 引用和取消负责人齐备后，才开启真实模型探针。
