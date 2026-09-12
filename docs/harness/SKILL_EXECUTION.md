# Skill、脚本和工具的执行边界

状态：本地确定性样例已实现；Claude SDK 接入仍为 P1 Proposed。

## 当前样例

项目包位于 `skills/csv-group-analysis/`，只有 SKILL.md 和 stdlib 脚本。不会修改个人配置、自动注册 SDK 工具或开放网络。

```sh
.venv/bin/python skills/csv-group-analysis/scripts/aggregate.py \
  --input examples/sales.csv --output .local/group-result.json \
  --group-by region --metric revenue --operation sum
```

执行前检查 CSV 实际列名；输出父目录须由调用方预先创建，已有输出拒绝覆盖。CLI 输出简短 JSON 引用；文件包含输入哈希、十进制指标、行数、缺失数量与口径。支持 UTF-8 CSV，最多 2 MiB/20,000 行/100 列/50 组。count 只统计非空有效数值；非法数值报错，不静默跳过。测试覆盖五类聚合、浮点误差规避、空表、字段错误和禁止覆盖。

该样例不是完整研报生成器，没有联网抓取、财务口径推断、模型调用、Skill 自动发现或一键发布。用户已批准的固定脚本可在本机验证；任意模型生成代码只能通过已验证隔离执行器运行。

## 目标职责

| 层 | 责任 | 不能代替 |
|---|---|---|
| Skill | 方法、输入语义、步骤提示、引用和模板 | 授权、强制状态机 |
| 确定性脚本/CLI | 文件转换、计算、产物生成 | SDK Loop、平台批准 |
| 受控工具 | 共享能力、外部数据访问、稳定输入输出契约 | 沙箱和租户隔离 |
| 平台 | 固定阶段门禁、权限、预算、持久状态、验收 | 引擎内部推理 |

固定顺序由代码执行，开放式分析由模型选择。Skill 与 CLI 不绕过 Tool Runtime；通过 Bash 调用仍属于可审计执行动作。工具与脚本共享核心函数时，不复制业务逻辑。

## P1 接入约束

- SDK/CLI/Skill/脚本固定版本与摘要，加载目录明确列出，不隐式继承开发者个人配置。
- Skills 在受控工作区按需加载；不得把文档中的授权声明当作运行时许可。
- 财经来源访问经有网络授权的工具服务执行；离线分析沙箱保持禁网。
- 工具结果和脚本 stdout 都设预算；只返回摘要与受控引用，不能返回宿主任意路径。
- SDK 会话压缩不改变原始数据、阶段产物、来源记录与平台任务状态。
- 引用、指标、权限、取消、恢复、重复执行和成本通过同一组探针后才能开放路由。

## 官方核验与未验证内容

官方文档支持 Skills 按需加载、自定义 MCP 工具和工具检索。工具检索与 Skills 解决不同层次的上下文占用，不能仅凭课程讲述认定它们是严格的历史先后阶段。2026-09-12 官方 Tool Search 页面描述默认启用（有模型/端点例外），10% 是 `ENABLE_TOOL_SEARCH=auto` 的阈值，而非所有配置的统一触发条件。实际参数仍以固定 SDK 版本探针为准，不把“10%”写成平台硬规则。

来源：[Skills](https://code.claude.com/docs/en/agent-sdk/skills)、[自定义工具](https://code.claude.com/docs/en/agent-sdk/custom-tools)、[Tool Search](https://code.claude.com/docs/en/agent-sdk/tool-search)。

对“五级压缩”的内部名称、50k 字符、5 分钟 TTL、必须 fork 子 Agent 等说法，本项目未验证，不作为实现依赖。[官方上下文说明](https://code.claude.com/docs/en/how-claude-code-works#when-context-fills-up)确认的是清理旧工具输出及必要时摘要，并提示早期细节可能丢失。
