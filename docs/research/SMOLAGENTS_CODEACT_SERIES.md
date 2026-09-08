# Smolagents / CodeAct 三篇材料阅读总结

## 材料范围

本记录覆盖三篇课程材料：

1. 《起点：从数据分析场景看 CodeAct 模式》，7 页。
2. 《核心：用 Smolagents 结合自定义工具完成数据分析报告生成》，6 页。
3. 《扩展：通过多 Agent 协同机制提升分析深度》，5 页。

课程材料用于提炼设计方法，不作为当前 SDK API 的唯一事实来源。版本敏感能力已与 Smolagents 官方文档交叉核对。

## 第一篇：CodeAct 为什么适合数据分析

传统工具调用模式需要把“读取、计算、绘图”等动作拆成很多预定义工具。工具越多，描述越长；每一步都经过模型往返，数据和中间结果持续挤占上下文。

CodeAct 的核心变化是让模型生成一段代码，由代码解释器一次完成组合、循环、变量传递、条件判断和异常处理。外层仍可以是“模型 → 动作 → 观察”的 Agent Loop，但动作语言从零散 JSON 调用变成代码。

适合场景：

- 任务可以用脚本高效表达；
- 步骤依赖数据实际形态，无法提前穷举；
- 需要表格处理、统计计算、绘图和文件产物；
- 中间对象较大，不适合反复塞回模型上下文。

不适合直接使用的边界：

- 写入生产系统、付款、发布等高风险副作用；
- 无法提供可靠隔离的任意代码执行；
- 流程完全固定、输出必须高度确定的事务链路；
- 数据规模更适合下推到数据库或计算引擎，而不是载入本地内存。

## 第二篇：工具、MCP 与报告生成

Smolagents 的 `CodeAgent` 将工具接口告知模型，并让生成代码在执行环境中调用这些工具。课程展示了两种扩展方式：

- 本地自定义工具：定义名称、描述、输入、输出和执行逻辑，适合项目内、低延迟、与适配器紧密相关的能力。
- MCP 工具：通过标准连接暴露工具，适合跨项目、跨运行时复用以及独立治理；可使用结构化输出。

文章中的 CSV 读取和 Markdown 写入只是演示。生产设计不能让模型自由选择任意文件路径：输入应先登记成不可变资源，输出只能写入受控产物目录，控制面保存摘要、来源和权限。

## 第三篇：主从 Agent 如何提升分析深度

课程用 `CodeAgent` 作为主 Agent 处理本地数据和整合报告，用 `ToolCallingAgent` 子 Agent 调用联网搜索。子 Agent 使用独立上下文完成专门任务，然后把结果交回主 Agent。

这个结构的价值不是“Agent 越多越好”，而是：

- 隔离不同任务的上下文和工具权限；
- 让本地计算与外部检索采用不同执行范式；
- 为子任务设置独立预算、超时、证据和失败策略；
- 主 Agent 只消费结构化结论与来源，不吞入全部搜索过程。

代价是更多模型调用、状态协调和错误路径。多 Agent 应在单 Agent 基线无法满足质量要求时再引入。

## 三篇合并后的设计结论

```text
受控资源 → CodeAgent 规划并生成分析代码
→ 隔离沙箱执行 → 结构化观察结果
→ 生成报告/图表产物 → 确定性检查与评测

后续可选：主 Run → 只读检索子 Run → 带来源的结构化结果 → 主 Run 综合
```

### 采用

- 把“数据分析报告”设为第一个具体纵向场景。
- P0 使用 CodeAct，但只开放很小的工具集。
- 将代码执行作为独立、不可信边界，默认禁网、限资源、只读输入。
- 区分项目内工具与可复用 MCP 工具，均由平台策略统一授权。
- 将子 Agent 映射为显式 Child Run，单独记录上下文、预算和 trace。

### 不直接采用

- 不在宿主进程使用 Python `exec` 执行模型代码。
- 不把本地 AST 解释器视为强安全沙箱。
- 不让 Agent 直接读写任意宿主路径。
- 不把联网搜索或多 Agent 放入最小 P0。
- 不根据课程截图锁定 SDK 版本、类名或参数。

## 官方资料核验

- [Smolagents Agents reference](https://huggingface.co/docs/smolagents/reference/agents)：当前官方仍提供 `CodeAgent`、`ToolCallingAgent`、`managed_agents` 和多种 executor。
- [Secure code execution](https://huggingface.co/docs/smolagents/main/tutorials/secure_code_execution)：官方明确指出本地执行仍有固有风险，强隔离应使用远程执行方案，并配置资源、网络和清理约束。
- [Python executors reference](https://huggingface.co/docs/smolagents/reference/python_executors)：`LocalPythonExecutor` 不是不可信代码的安全边界；远程执行还需避免不安全序列化。
- [Tools and MCP reference](https://huggingface.co/docs/smolagents/reference/tools)：MCP Client 支持 Stdio、Streamable HTTP 与结构化输出，并需要显式管理连接生命周期。

## 对 HarnessAgent 的直接影响

1. P0 从抽象“通用平台”收敛为可复现的表格数据分析链路。
2. Smolagents 是首个候选真实适配器，但在官方版本、许可和原型验证完成前保持 Proposed。
3. Task 只表示用户意图，Run 表示一次执行；子 Agent 是 Child Run。
4. 适配器不能直写业务存储，只通过事件、检查点和产物契约汇报。
5. 沙箱、工具权限、产物路径和预算进入核心契约，而非实现细节。
