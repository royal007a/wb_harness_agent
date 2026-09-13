# API 规格

当前本地 v0.1 实现范围、JSON 事件轮询和简化表单端点见 [LOCAL_WORKBENCH.md](LOCAL_WORKBENCH.md)。下文为完整目标规格，未实现接口不能据此视为可调用。

> P0 机器契约以 `specs/v1/openapi.yaml` 与 `specs/v1/core-contracts.schema.json` 为准；ADR-0019 的本地受限 Replan 还引用 `execution-control.schema.json` 与 `local-replan.schema.json`。本文是与其同步维护的叙事说明。它们若漂移，HA-0001 不得冻结。

## 通用约定

- 基础路径：`/api/v1`
- 数据格式：`application/json; charset=utf-8`
- 流式事件：Server-Sent Events，`text/event-stream`
- 身份：短期访问令牌；服务端从身份上下文解析 `workspace_id`
- 幂等：创建任务和批准操作必须携带 `Idempotency-Key`
- 并发：更新资源使用 `If-Match` 与版本号
- 时间：RFC 3339 UTC；ID 使用不可枚举的全局唯一标识
- 分页：游标分页，稳定排序；响应包含 `next_cursor`

## 路线图资源接口

下表是完整目标面，不代表 P0 全部实现；`specs/v1/openapi.yaml` 当前覆盖 Task/Run、事件、取消、批准，以及 ADR-0019 的本地白名单 Replan TCC Draft。

| 资源 | 阶段 | 主要接口 | 说明 |
|---|---|---|---|
| Projects | P0-min | `POST/GET /projects` | 项目和环境边界 |
| Agent Specs | P0-min | `POST/GET /agent-specs` | 版本化 Agent 定义 |
| Engines | P0 | `GET /engines` | 能力、限制、健康和版本 |
| Model Routes | P0-min / P0.1 | `GET /model-routes` | 模态到逻辑模型与部署的显式映射 |
| Skills | P1 | `POST/GET /skills` | 版本化技能包与元数据 |
| Tools | P0 | `POST/GET /tools` | 输入输出 Schema、风险等级 |
| MCP Servers | P1 | `POST/GET /mcp-servers` | 连接配置的密钥引用 |
| 外部连接器 | P1 | `GET/POST /local/connectors/{provider}` | 本地开发连接状态与显式 OAuth 授权 |
| Local Agent Lab | ADR-0021 本地准备 | `GET/POST /local/agent-lab/*` | 无密配置、Session 与确定性 POST SSE；不调用模型/Provider |
| Resources | P0 | `POST/GET /resources` | 文件、数据源和上下文引用 |
| Tasks | P0 | `POST/GET /tasks` | 提交、查询与列表 |
| Runs | P0 | `POST/GET /tasks/{id}/runs` | 创建和查询执行尝试 |
| Run Events | P0 | `GET /runs/{id}/events` | SSE 或游标拉取 |
| Artifacts | P0 | `GET /tasks/{id}/artifacts` | 结果、文件、引用和摘要 |
| Approvals | P1 | `POST /approvals/{id}:decide` | 批准或拒绝一次动作 |
| Workflows | P2 | `POST/GET /workflows` | 后续 DAG 能力 |
| Plan Revisions / Replans | P1 | `POST/GET /runs/{id}/replans` | 版本化计划、Evidence/Gap Gate 与受控恢复；本地仅实现 ADR-0019 的白名单 TCC 切片 |
| Evaluations | P0 | `POST/GET /evaluations` | 数据集、运行和比较 |

## 创建任务

`POST /api/v1/tasks`

```json
{
  "project_id": "prj_01",
  "agent_spec_version": "agent_01@3",
  "objective": "根据给定资料生成带引用的比较报告",
  "engine_policy": {
    "mode": "explicit",
    "engine_id": "engine_smolagents_code",
    "required_capabilities": ["actions.code", "artifacts.files"]
  },
  "model_policy": {
    "text_and_code": "model_unresolved",
    "vision": null,
    "allow_fallback": false
  },
  "context": {
    "resource_ids": ["res_01"],
    "variables": {"language": "zh-CN"}
  },
  "limits": {
    "max_turns": 20,
    "timeout_seconds": 900,
    "max_input_tokens": 100000,
    "max_cost_minor": 5000
  },
  "requested_permissions": {
    "profile": "analysis_read_only",
    "profile_version": 1,
    "allow_tools": ["resource.inspect", "artifact.publish", "run.final_answer"],
    "deny_capabilities": ["network", "external_write", "package_install"]
  },
  "metadata": {"request_source": "console"}
}
```

成功返回 `202 Accepted`：

```json
{
  "task": {
    "id": "task_01",
    "project_id": "prj_01",
    "parent_task_id": null,
    "objective": "根据给定资料生成带引用的比较报告",
    "agent_spec_version": "agent_01@3",
    "context": {
      "resource_ids": ["res_01"],
      "variables": {"language": "zh-CN"}
    },
    "engine_policy": {
      "mode": "explicit",
      "engine_id": "engine_smolagents_code",
      "required_capabilities": ["actions.code", "artifacts.files"]
    },
    "model_policy": {
      "text_and_code": "model_unresolved",
      "vision": null,
      "allow_fallback": false
    },
    "requested_permissions": {
      "profile": "analysis_read_only",
      "profile_version": 1,
      "allow_tools": ["resource.inspect", "artifact.publish", "run.final_answer"],
      "deny_capabilities": ["network", "external_write", "package_install"]
    },
    "limits": {
      "max_turns": 20,
      "timeout_seconds": 900,
      "max_input_tokens": 100000,
      "max_cost_minor": 5000
    },
    "metadata": {"request_source": "console"},
    "created_at": "2026-09-08T08:00:00Z"
  },
  "initial_run": {
    "id": "run_01",
    "task_id": "task_01",
    "status": "queued",
    "selected_engine": "engine_smolagents_code",
    "selected_models": {
      "text_and_code": "model_unresolved"
    },
    "effective_permissions": {
      "profile_id": "analysis_read_only",
      "profile_version": 1,
      "allowed_tools": ["resource.inspect", "artifact.publish", "run.final_answer"],
      "denied_capabilities": ["network", "external_write", "package_install"],
      "decision_digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    },
    "effective_limits": {
      "max_turns": 20,
      "timeout_seconds": 900,
      "max_input_tokens": 100000,
      "max_cost_minor": 5000
    },
    "attempt_number": 1,
    "latest_sequence": 0,
    "exit_reason": null,
    "created_at": "2026-09-08T08:00:00Z",
    "updated_at": "2026-09-08T08:00:00Z"
  },
  "links": {
    "task": "/api/v1/tasks/task_01",
    "run": "/api/v1/runs/run_01",
    "events": "/api/v1/runs/run_01/events"
  }
}
```

## 本地意图预检（已实现的受限入口）

`POST /api/local/intents:interpret` 不持久化请求，也不需要幂等键。它不创建 Task 或 Run，仅检查当前本地工作台是否能理解该输入：

```json
{"objective":"检查 CSV 数据质量","resource_id":"res_..."}
```

结果符合 `specs/v1/intent-contract.schema.json`。`ready` 仅建议固定 `engine_mock_analytics`，并要求 `explicit_user_submit`；`clarification_required` 返回缺少的 `resource_id` 和固定提问；`rejected` 不猜测或路由至其他能力。响应不回显 `objective` 原文，只返回摘要与长度，`model_calls` 恒为 0。

`POST /api/local/tasks` 在创建前会重做该预检：缺槽返回 `INTENT_CLARIFICATION_REQUIRED`，不支持请求返回 `INTENT_REJECTED`。严格 `POST /api/v1/tasks` 保持显式 Task/引擎契约，不被该本地便利入口改写。

## Local Agent Lab（ADR-0021 已实现，零模型调用）

该独立本机端点不属于 `/api/v1` Product Task/Run 面：

- `GET/POST /api/local/agent-lab/providers`：无密 Provider Profile；只接受 `name/type/base_url/enabled`。
- `GET/POST /api/local/agent-lab/models`：Model Profile；必须引用已启用 Provider。
- `GET/POST /api/local/agent-lab/agents`：Agent 配置模板；必须引用已启用 Model，工具绑定恒为 0。
- `GET/POST /api/local/agent-lab/sessions`，`GET /api/local/agent-lab/sessions/{id}`：本地有状态会话与有序纯文本消息。
- `POST /api/local/agent-lab/sessions/{id}/messages`：请求要求 `Accept: text/event-stream` 与 `Idempotency-Key`，返回 `delta` 后接 `done`。响应固定声明 `model_calls=provider_calls=0`。

请求/响应以 [`local-agent-lab.schema.json`](../../specs/v1/local-agent-lab.schema.json) 为准。未知字段、凭证样式输入、外部 HTTP 地址、禁用依赖、归档会话和幂等键冲突使用稳定错误信号拒绝。Base URL 不会被连通性测试或模型请求使用。此路径不产生 Product Event/Evidence，也不能读写 Task、Run、Plan、权限或预算。

## Task 与 Run 动作

- `GET /tasks/{id}`：返回不可变 Task 和独立的 `latest_run` 快照；列表接口可另行提供派生的 `latest_run_status`。
- `POST /tasks/{id}/runs`：基于同一 Task 创建新 Run；可提供 `based_on_run_id` 和 `reason`。
- `POST /runs/{id}:cancel`：幂等取消一个非终态 Run。
- `GET /runs/{id}`：返回 Run 状态、版本、限制消耗、结果摘要和链接。
- `GET /runs/{id}/events`：使用 SSE 或游标读取该 Run 的事件。

本地 v0.1 另实现一个更窄的恢复接口：`GET /api/local/runs/{id}/restore` 只返回当前 Checkpoint 是否可恢复；`POST /api/local/runs/{id}:restore` 接受空 JSON 对象和 `Idempotency-Key`，只允许 `engine_mock_analytics` 的 `failed`/`expired` 源 Run 创建同 Task 的新恢复 Run。调用方不能提交 Plan、资源、目标、权限或预算；任何摘要绑定不兼容返回稳定错误码且不创建 Run。它不是以下动态 Replan 目标接口的替代。

面向用户的 API 不提供 `resume`。批准后控制面校验 Checkpoint，并自动重新投递同一 Run；服务故障恢复属于内部协议。

## Plan / Replan（本地受限切片 + 通用目标）

动态执行器通过 `PlanRevision` 绑定一个 Run 的候选 Action、硬前置条件和 Evidence 要求。`ReplanAttempt` 是 Run 的独立控制对象，不能修改原 Task 或终态 Run：

- `POST /runs/{id}/replans`：基于已记录失败事件创建 `proposed` Attempt；请求必须指定失败事件、候选计划摘要与回滚 Checkpoint 引用。
- `POST /replans/{id}:try`：仅运行无副作用的兼容性/权限/剩余预算/失效集合校验。
- `POST /replans/{id}:confirm`：以计划、checkpoint、适配器/工具/资源、权限和剩余预算摘要的比较并交换确认；成功才创建新的恢复 Run。
- `POST /replans/{id}:cancel`：仅取消该 Attempt 并使确认失效，不取消原 Run，也不自动补偿。

ADR-0019 已把同一路径以受限本地接口接入：`POST/GET /api/v1/runs/{id}/replans`、`GET /api/v1/replans/{id}` 与 `POST /api/v1/replans/{id}:try|confirm|cancel`。所有写入请求都使用空 JSON 对象和 `Idempotency-Key`。控制面只接受 `ARTIFACT_PUBLICATION_FAILED` 的固定分析源 Run，并自行派生唯一候选计划；Try 无副作用，Confirm 才创建恢复 Run，Cancel 只废弃 Attempt。调用者不能提交目标、Plan、资源、权限、预算、Prompt 或代码。

除上述白名单路径外，通用接口在当前本地 v0.1 **仍不存在**。只有声明并验证 checkpoint、restore、cancel 的适配器可申请扩展。完整合同与六出口见 [Plan / Replan 执行控制](PLAN_REPLAN_CONTROL.md)。

## 本地百度网盘 OAuth 连接器

已实现的本地接口只用于 OAuth 连接准备，数据面仍关闭：

- `GET /api/local/connectors/baidu-netdisk`：返回脱敏连接状态；不返回 App Secret 或 token。
- `POST /api/local/connectors/baidu-netdisk/authorization`：空 JSON 对象与 `Idempotency-Key`；创建或重放同一短期授权 URL。
- `GET /api/local/connectors/baidu-netdisk/callback`：百度顶级页面重定向的唯一跨站 GET 入口；state 单次、十分钟有效。该接口只返回静态成功/失败页面。
- `POST /api/local/connectors/baidu-netdisk:disconnect`：空 JSON 对象与 `Idempotency-Key`；删除本机 Keychain token，不影响百度账户或网盘文件。删除动作本身天然幂等，故不把 Keychain 的外部副作用包进 SQLite 重放事务。

固定端点、scope 和凭证说明见 [BAIDU_NETDISK_CONNECTOR.md](BAIDU_NETDISK_CONNECTOR.md)。未配置应用时返回 `CONNECTOR_NOT_CONFIGURED`；state 错配、重放/过期及令牌错误使用稳定 `AUTHORIZATION_STATE_*` / `OAUTH_*` 错误码。无公开分享链接下载 API。

## 事件包络

```json
{
  "event_id": "evt_01",
  "event_type": "tool.call.completed",
  "event_version": 1,
  "workspace_id": "ws_01",
  "project_id": "prj_01",
  "task_id": "task_01",
  "run_id": "run_01",
  "sequence": 18,
  "occurred_at": "2026-09-08T08:01:12Z",
  "trace_id": "trace_01",
  "data": {}
}
```

事件只追加；消费者以 `(run_id, sequence)` 去重。敏感输入只记录摘要、分类和受控引用。

SSE 客户端使用 `Last-Event-ID` 恢复；服务端必须说明事件保留期、心跳间隔和慢消费者断开语义。超出保留期返回 `EVENT_CURSOR_EXPIRED`，客户端转用 Run 快照后重新订阅。

## 批准动作

`POST /api/v1/approvals/{approval_id}:decide`

```json
{
  "decision": "approved",
  "reason": "已核对目标与影响范围",
  "constraints": {
    "expires_at": "2026-09-08T09:00:00Z",
    "max_uses": 1
  }
}
```

批准绑定动作摘要、工具版本、参数摘要、Task 和 Run；参数变化后必须重新批准。决定只有 `approved` 或 `rejected`，主体从认证上下文获得。重复相同决定幂等，冲突决定返回 `409 APPROVAL_ALREADY_DECIDED`。批准成功后由控制面自动恢复 Run。

## 错误格式

```json
{
  "error": {
    "code": "PERMISSION_REQUIRED",
    "message": "该动作需要人工批准",
    "retryable": false,
    "request_id": "req_01",
    "details": {"approval_id": "apr_01"}
  }
}
```

稳定错误码至少包括 `VALIDATION_ERROR`、`UNAUTHENTICATED`、`FORBIDDEN`、`NOT_FOUND`、`CONFLICT`、`RATE_LIMITED`、`ENGINE_UNAVAILABLE`、`MODEL_CAPABILITY_MISMATCH`、`PERMISSION_REQUIRED`、`BUDGET_EXCEEDED`、`CHECKPOINT_NOT_FOUND`、`CHECKPOINT_NOT_RESTORABLE`、`CHECKPOINT_INCOMPATIBLE`、`CHECKPOINT_STATE_INVALID`、`EVENT_CURSOR_EXPIRED`、`SANDBOX_VIOLATION`、`TIMEOUT` 和 `INTERNAL_ERROR`。

## 兼容规则

- 同一主版本只允许新增可选字段和新事件类型。
- 删除、改义、收紧枚举或改变默认值必须升主版本。
- 客户端必须忽略未知可选字段，但不能忽略未知终态。
- 适配器私有字段放入命名空间扩展区，不进入核心契约。

核心对象语义见 [CORE_CONTRACTS.md](CORE_CONTRACTS.md)，内部适配器语义见 [ADAPTER_CONTRACT.md](ADAPTER_CONTRACT.md)，工具和沙箱边界见 [TOOL_AND_SANDBOX.md](TOOL_AND_SANDBOX.md)。机器可读 Draft 位于 `specs/v1/`，须在 HA-0001 评审、探针和契约测试后才能冻结；本文不是已实现 API。
