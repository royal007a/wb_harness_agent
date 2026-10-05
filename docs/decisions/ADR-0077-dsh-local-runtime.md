# ADR-0077：独立 DSH 本地业务运行路径

日期：2026-10-05。状态：用户授权实现本地分支。

用户要求两小时内新建 DSH 分支、实现基于 DSH 的方式、本地部署并给 URL，交 mymacclaude review。

在 dsh/local-runtime-20261005 分支上实现独立本地工作台入口，运行官方固定版本 DSH Agent Loop，而不是把另一个循环改名为 DSH。复用平台 Task/Run、事件、产物和取消语义；模型/工具入口显式选择，不替换既有引擎。独立数据库、进程和端口（计划8876），不修改主分支8765或132。用户本轮明确只要求本地，故不执行双端发布。

优先使用 DSH sdk-minimal + 显式覆盖配置：移除 shell/文件/子代理/自扩展等能力，禁用遥测和自动重试、压缩；平台只读固定工具。模型调用采用受控平台传输；真实模型需已有授权的固定端点及安全凭据引用，无凭据时明确拒绝，不使用脚本回复冒充真实模型。

平台事件只留元数据；模型正文经受控产物发布。来源必须用平台签发标识，不能用模型自由字符串作为事件 evidence_ref（HA-0076 review 所示旁路不得引入新引擎）。DSH 自有日志位于隔离 Run 目录，有界生命周期，不读取默认 ~/.dsh。

验收：实际 DSH 进程/SDK 协议、工具循环、正常及取消/超时/预算/错误路径；浏览器可访问的新本地 URL，版本和健康可核对；固定提交独立 review。分别报告真实 DSH+合成 Provider、真实 Provider、浏览器及部署证据，不混淆。

## 本分支真实 Provider 的窄边界

沿用 ADR-0074 的用户用途声明、固定 Coding Plan URL、模型和每 Run 2000 万 Token 上限；不改变任何既有 Pi/Claude Gate。凭证来自用户指定消息，只保存到 Keychain `harnessagent / dsh-ark-coding-local-20261005`，DSH 只获得短期 loopback capability。

2026-10-05 核对[官方模型配置](https://docs.volcengine.com/docs/ark/coding-plan-personal-ai-zcode?lang=zh)：lite 上下文 1,024,000、最大输出 256,000。每次真实请求预留完整 1,024,000 输入 + 256,000 输出，不依赖 tokenizer/字符估算；实际请求仍固定 max_tokens≤2048。每 Run 最多8次请求，无压缩/重试/辅助调用；没有可靠 usage 则冻结，不退款重发。这是在官方服务遵守公开模型上限前提下的保守边界，不声称平台能强制约束远端计费实现。

[官方套餐概览](https://docs.volcengine.com/docs/ark/coding-plan-personal-plan-overview?lang=zh)说明指定 Coding URL 用尽额度后等待刷新，不扣其他资源包或余额。故本窄路由仅允许已订阅额度，max_cost_minor=0 表示不批准余额付费，不表示请求没有订阅成本；不得跳转、换 URL 或回退按量计费。仍保留官方对非编码用途的限制说明，业务使用资格依 ADR-0074 用户声明，不能把本测试当作套餐权益证明。

仅公开/合成文本；两项文档工具无任意外网/文件能力。真实执行需要 HARNESS_DSH_REAL_ENABLED=1 和受控 credential_ref，不自动继承 ARK_API_KEY。DSH不是 OS 沙箱，允许集合不是恶意上游代码隔离证明。此切片的 succeeded 只表示技术执行完成，产物为需人工复核的草稿，不是合同/投资结论已批准。
