# API 规格

当前本地 v0.1 实现范围、JSON 事件轮询和简化表单端点见 [LOCAL_WORKBENCH.md](LOCAL_WORKBENCH.md)。下文为完整目标规格，未实现接口不能据此视为可调用。

> P0 机器契约以 `specs/v1/openapi.yaml` 与 `specs/v1/core-contracts.schema.json` 为准；本文是与其同步维护的叙事说明。两者若漂移，HA-0001 不得冻结。

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

下表是完整目标面，不代表 P0 全部实现；`specs/v1/openapi.yaml` 当前只覆盖 Task/Run、事件、取消与批准的 P0 Draft。

| 资源 | 阶段 | 主要接口 | 说明 |
|---|---|---|---|
| Projects | P0-min | `POST/GET /projects` | 项目和环境边界 |
| Agent Specs | P0-min | `POST/GET /agent-specs` | 版本化 Agent 定义 |
| Engines | P0 | `GET /engines` | 能力、限制、健康和版本 |
| Model Routes | P0-min / P0.1 | `GET /model-routes` | 模态到逻辑模型与部署的显式映射 |
| Skills | P1 | `POST/GET /skills` | 版本化技能包与元数据 |
| Tools | P0 | `POST/GET /tools` | 输入输出 Schema、风险等级 |
| MCP Servers | P1 | `POST/GET /mcp-servers` | 连接配置的密钥引用 |
| Resources | P0 | `POST/GET /resources` | 文件、数据源和上下文引用 |
| Tasks | P0 | `POST/GET /tasks` | 提交、查询与列表 |
| Runs | P0 | `POST/GET /tasks/{id}/runs` | 创建和查询执行尝试 |
| Run Events | P0 | `GET /runs/{id}/events` | SSE 或游标拉取 |
| Artifacts | P0 | `GET /tasks/{id}/artifacts` | 结果、文件、引用和摘要 |
| Approvals | P1 | `POST /approvals/{id}:decide` | 批准或拒绝一次动作 |
| Workflows | P2 | `POST/GET /workflows` | 后续 DAG 能力 |
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

## Task 与 Run 动作

- `GET /tasks/{id}`：返回不可变 Task 和独立的 `latest_run` 快照；列表接口可另行提供派生的 `latest_run_status`。
- `POST /tasks/{id}/runs`：基于同一 Task 创建新 Run；可提供 `based_on_run_id` 和 `reason`。
- `POST /runs/{id}:cancel`：幂等取消一个非终态 Run。
- `GET /runs/{id}`：返回 Run 状态、版本、限制消耗、结果摘要和链接。
- `GET /runs/{id}/events`：使用 SSE 或游标读取该 Run 的事件。

面向用户的 API 不提供 `resume`。批准后控制面校验 Checkpoint，并自动重新投递同一 Run；服务故障恢复属于内部协议。

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

稳定错误码至少包括 `VALIDATION_ERROR`、`UNAUTHENTICATED`、`FORBIDDEN`、`NOT_FOUND`、`CONFLICT`、`RATE_LIMITED`、`ENGINE_UNAVAILABLE`、`MODEL_CAPABILITY_MISMATCH`、`PERMISSION_REQUIRED`、`BUDGET_EXCEEDED`、`EVENT_CURSOR_EXPIRED`、`SANDBOX_VIOLATION`、`TIMEOUT` 和 `INTERNAL_ERROR`。

## 兼容规则

- 同一主版本只允许新增可选字段和新事件类型。
- 删除、改义、收紧枚举或改变默认值必须升主版本。
- 客户端必须忽略未知可选字段，但不能忽略未知终态。
- 适配器私有字段放入命名空间扩展区，不进入核心契约。

核心对象语义见 [CORE_CONTRACTS.md](CORE_CONTRACTS.md)，内部适配器语义见 [ADAPTER_CONTRACT.md](ADAPTER_CONTRACT.md)，工具和沙箱边界见 [TOOL_AND_SANDBOX.md](TOOL_AND_SANDBOX.md)。机器可读 Draft 位于 `specs/v1/`，须在 HA-0001 评审、探针和契约测试后才能冻结；本文不是已实现 API。
