# API 规格

HA-0058 修复动态 OpenAPI 的契约归属：Lab、Runtime、研究模拟使用独立 component
命名空间，注册时拒绝同名不同义；Lab/Runtime 的列表、状态、详情、readiness 与
创建响应均引用本域 JSON Schema，静态 OpenAPI 同源。请求 JSON 和持久 ID 不变，
旧错误 component 名不保留别名，客户端生成器需重新生成。实例验证范围与边界见
[OpenAPI 合同验收](../../specs/testing/OPENAPI_CONTRACTS.md)，不代表所有接口已验收。

## 当前核心 Product HTTP 合同（HA-0062）

静态 OpenAPI 和运行时 `/openapi.json` 共用 core bundle 的 `local_http_*` 封装；
该范围的 HTTP 行为不变，修正的是原先错写或空缺的公开文档。旧客户端须重新生成。

| 接口 | 当前响应 |
|---|---|
| POST tasks / local/tasks | 202，`{task,initial_run}`，没有 links |
| GET tasks / tasks/{id} | 列表 `{items:[{task,latest_run}]}`；详情 `{task,runs}` |
| POST tasks/{id}/runs | 202，新 Run；reason 可省略，不限定 retry/rerun 枚举 |
| POST runs/{id}:cancel | 200，Run；不要求幂等键，已终态保持不变 |
| GET runs/{id}/events | JSON `{items,next_cursor}`，0≤after≤9223372036854775807，越界422，每页最多500；非 SSE |
| GET/POST resources、GET resources/{id}、POST native/documents | 本地 CSV/合成 JSON/Public PDF 登记元数据，不是未来 ResourceHandle |
| GET Run/Task artifacts、下载 / sample | 列表 metadata；下载实际 media_type，sample 为 text/csv，不是 JSON |
| 上述入口错误 | `{error:{code,message,retryable:false,request_id}}`，不是 FastAPI detail 默认体 |

health 是静态存活声明，不是 Provider 调用计数或发布身份。验收与未覆盖范围见
[Product HTTP 测试合同](../../specs/testing/PRODUCT_HTTP_CONTRACTS.md)。其余模块空响应
Schema 仍需逐项补齐，不据此称全 API 已验收。

当前本地 v0.1 实现范围、JSON 事件轮询和简化表单端点见 [LOCAL_WORKBENCH.md](LOCAL_WORKBENCH.md)。
**以下为完整目标规格与历史示意（包括 links、SSE、认证等），不是当前响应样本；与上表
冲突时以当前机器契约为准。未实现接口不能据此视为可调用。**

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
| Local Agent Runtime | ADR-0022 受控聊天运行时 | `GET/POST /local/agent-runtime/*` | 独立 Provider/Model/Agent/Session/Exchange、上下文窗口与 POST SSE；默认外部模型调用关闭 |
| Research Agent Simulation | ADR-0023 本地模拟切片 | `GET/POST /local/research-agents` | 三角色 Child Agent、Skill/Tool 快照与父级证据汇总；模型和网络调用为零 |
| Native Claude Research | ADR-0024 Proposed 受控准入 | `GET/POST /local/research-native*` | 原生 SubAgent、第一方插件 Skills、进程内 MCP 资料工具；默认所有外部调用关闭 |
| Pi Contract Pipeline | HA-0043/0044/0046 已实现的离线切片 | `POST /local/pi-contract-pipeline/preview`、`/review`、`/review-stream` | Public PDF 解析/分类/分块、确定性 Skill 候选与 SSE 事件适配；始终人工 Gate，模型/网络调用为零 |
| Pi Security Guard | HA-0045 课程 20 metadata-only 护栏 | `POST /local/pi-contract-pipeline/security-check` | 对 tool_call/tool_result/context/provider_request 做确定性准入判断；未知能力、越权路径、非白名单域名、敏感内容与预算超限 fail-closed；不执行动作 |
| Team Session Continuity | ADR-0037 Proposed 受限控制面 | `GET/POST /local/team/sessions*` | Team Session、手工 Handoff 与无正文当前工作摘要；不连接模型/Runtime Session |
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

## Local Agent Runtime（ADR-0022）

- `GET/POST /api/local/agent-runtime/providers`：保存协议类型、无密 Base URL 与可选 `keychain://harnessagent/<name>` 引用；`GET /providers/{id}/readiness` 只解释激活状态，网络调用恒为 0。
- `GET/POST /api/local/agent-runtime/models`、`agents`：显式 Provider→Model→Agent 配置链；Agent 的工具绑定恒为 0。
- `GET/POST /api/local/agent-runtime/sessions`、`GET /sessions/{id}`：独立、有序的消息与 Exchange 历史。
- `POST /sessions/{id}/messages`：要求 `Accept: text/event-stream` 和 `Idempotency-Key`，输出 `delta`、`done` 或 `error`。默认产生 `MODEL_RUNTIME_DISABLED`，并且不会写 assistant 演示文本。

请求/响应以 [`agent-runtime.schema.json`](../../specs/v1/agent-runtime.schema.json) 为准。Provider Adapter 仅翻译协议；外部请求还要求环境开关、可用引用与 Keychain 解析，详见 [Agent Runtime](AGENT_RUNTIME.md)。该路径不读写 Product Task/Run/Plan/Evidence/Checkpoint。

HA-0057：上游流必须有正常 stop 与完整 DONE，才可能发送下游 done。EOF、不完整
终止、length 截断、过滤/工具/拒绝输出及畸形协议通过既有 SSE error.error_code 返回，
并持久化 failed；已发 delta 仍只是预览，不写 assistant。错误码和协议限额见
[PROVIDER_STREAM](../../specs/testing/PROVIDER_STREAM.md)，没有新增端点或放宽运行门禁。
请求上游固定 Accept-Encoding: identity；出现任意 Content-Encoding 响应头，
读取正文前即以 MODEL_PROVIDER_INVALID_RESPONSE 失败，不自动解压或重试。

## External Skill Runtime（ADR-0025，默认关闭）

- `GET /api/local/external-skills/runtime`：返回 `external-skill-runtime@1` 状态、固定隔离 profile、镜像是否就绪和 blocker；不会读包或创建容器。
- `GET /api/local/external-skills/packages`：列出已登记的不可变 package 摘要及运行时状态。
- `POST /api/local/external-skills/packages?source_label=<label>`：要求 `application/zip` 与 `Idempotency-Key`，只登记严格 `manifest.json + entry.py` 包；登记不执行代码。
- `POST /api/local/external-skills/packages/{package_id}:execute`：要求 `Idempotency-Key`，输入为 `{"input": {...}}`。仅当 `HARNESS_EXTERNAL_SKILLS=enabled` 时，才会复核 package SHA-256 并在一次性禁网非 root 容器执行。

请求与结果以 [`external-skill-runtime.schema.json`](../../specs/v1/external-skill-runtime.schema.json) 为准。该 local-admin 切片没有 URL/Git/包管理器/网络/凭证/模型/MCP/Task/Run 权限；它的审计记录不作为 Product Event。详见 [外部 Skill 隔离运行时](EXTERNAL_SKILL_RUNTIME.md)。

## Memory Plane M1 + Context M2-A + Graph M3-A + Entity Catalog M3-B（ADR-0026/0027/0028/0029，本机受限实现）

- `GET /api/local/memory/runtime`：返回 `memory-plane-m3b@1` 的能力边界；显示可重建的 SQLite FTS5 关键词投影、显式 SQLite relation store、exact Entity Catalog 和 M2-B semantic retrieval Admission Gate。当前 Gate 固定 `not_admitted`，`runtime_enabled=false`、模型/外部调用均为 0；模型抽取、Reflect、vector、自动 Entity Resolution、自然语言 GraphQA、Product Task/Run 集成均为关闭或未实现。
- `GET/POST /api/local/memory/banks`：创建并列出固定 `ws_local` / `local_admin` 的 Bank；写入需 `Idempotency-Key`，不接受调用方指定 workspace/owner。
- `GET /api/local/memory/banks/{bank_id}`：返回不含 Source 正文的 Bank 元数据与 source/fact 计数。
- `POST /api/local/memory/banks/{bank_id}/retain`：写入显式 Source Evidence 与调用方已抽取的原子 Facts；需要 `Idempotency-Key`。无模型抽取，Restricted/凭证样式内容、Public Bank 的 Internal Source 与跨 Bank supersede 均拒绝。
- `POST /api/local/memory/banks/{bank_id}/entities`：以一个 active、同 Bank Fact 显式登记 Entity，返回 `entity_id`；不按名称查找、合并或自动抽取。
- `POST /api/local/memory/banks/{bank_id}/relations`：以一个 active、同 Bank Fact 显式登记有向 Relation；两端 Entity 必须属于同 Bank 且仍有效。
- `POST /api/local/memory/banks/{bank_id}:recall`：无副作用的 keyword/temporal read-back，返回不带 Source 正文的 `evidence-bundle@1`。`as_of` 同时过滤 Source `occurred_at`、Fact `occurred_at` 和 Fact 有效期；没有可见 evidence 只表示该时点无可读证据。
- `POST /api/local/memory/banks/{bank_id}:context`：接收调用方暂时提供的最近至多 8 轮与查询，返回 `memory-context-capsule@1`。最近轮不入库；摘要由受限 Fact 派生、目录只给可选择的 evidence ID，既不读原始 Source 正文也不调用模型；它与 Recall 使用同一 `as_of` 可见性过滤。
- `POST /api/local/memory/banks/{bank_id}:recall-details`：最多按 8 个目录 evidence ID 再次验证 Bank、Source/Fact 状态、发生时间和有效期，再返回有界显式 Fact detail 与 Source 引用；无效、未来或跨 Bank ID 只返回不可用，不泄露正文。
- `POST /api/local/memory/banks/{bank_id}:graph-recall`：接收已知 `start_entity_id`，在 active、同 Bank、有效的 Entity/Relation 上最多走两跳，返回每条 edge 的 Fact/Source 引用。它不接受自然语言、不做自动实体消歧，empty 仅表示当前可访问证据中无路径。
- `POST /api/local/memory/banks/{bank_id}:resolve-entity`：接收完整 canonical name 或已登记 alias，可选 `entity_type` / `as_of`；只以 casefold 精确相等返回 active、同 Bank、有效且 Fact/Source 可追溯的 `resolved` / `ambiguous` / `not_found` 候选。多候选绝不自动选择；调用方必须将候选 `entity_id` 显式交给 `:graph-recall`。结果不含原始 Source 正文。
- `POST /api/local/memory/banks/{bank_id}:fact-lineage`：接收已知 `fact_id`，最多回溯 8 层同 Bank supersede 历史。active 节点才标为 `current_applicable`，superseded 节点仅为 `historical`；Source/Fact 必须在 `as_of` 可见且 Source active。它不按自然语言寻找冲突、不自动裁决，也不返回 Source 正文。
- `POST /api/local/memory/sources/{source_id}:retract`：空 JSON + `Idempotency-Key`；将 Source 与依赖 active Facts 标记 retracted。`DELETE /api/local/memory/sources/{source_id}`：`Idempotency-Key`；删除可控正文/Fact 并留无正文 tombstone/audit。

请求与响应以 [`memory-plane.schema.json`](../../specs/v1/memory-plane.schema.json)、[`memory-context.schema.json`](../../specs/v1/memory-context.schema.json)、[`memory-graph.schema.json`](../../specs/v1/memory-graph.schema.json) 与 [`memory-entity-catalog.schema.json`](../../specs/v1/memory-entity-catalog.schema.json) 为准。它不替代权威事实源，也不是完整 RAG/Memory 系统；限制和生命周期见 [Memory Plane M1](MEMORY_PLANE_M1.md)、[Memory Context M2-A](MEMORY_CONTEXT_M2A.md)、[Memory Graph M3-A](MEMORY_GRAPH_M3A.md) 与 [Memory Entity Catalog M3-B](MEMORY_ENTITY_CATALOG_M3B.md)。

## Team Foundation（ADR-0035，本机协议授权边界）

- `GET /api/local/team/foundation/runtime`：明确返回 `protocol_identity_authentication=not_connected`、Agent Runtime 未连接、模型/工具调用为零、消息投递未实现。
- `GET/POST /api/local/team/workspaces`：按 protocol `actor_id` 返回可见 Workspace；创建仅允许本机 bootstrap `local_admin`，并不构成 HTTP 登录能力。
- `GET /api/local/team/workspaces/{workspace_id}`、`/agents`、`/channels`：必须具有 active Workspace membership；返回元数据/成员关系，不返回消息、Thread、私有 Agent state 或凭据。
- `POST /api/local/team/workspaces/{workspace_id}/agents`、`/memberships`、`/channels`：Workspace owner/admin 创建 Agent protocol identity、加入已有 identity 或创建 Channel；所有写入使用 `Idempotency-Key`。
- `GET /api/local/team/channels/{channel_id}`、`POST /api/local/team/channels/{channel_id}/memberships`：Channel 读取/role 授权需 Workspace membership、clearance 和 Channel membership；data class 为 `Public / Internal / Restricted`。

请求和响应以 [`team-foundation.schema.json`](../../specs/v1/team-foundation.schema.json) 为准。它不实现 token/OIDC、真实用户或 Agent 认证、消息/Thread/DM、Daemon、Computer、模型或工具权限执行；完整边界见 [Team Foundation](TEAM_FOUNDATION.md)。

## Team Attention（ADR-0036，本机受限控制面）

- `GET /api/local/team/attention/runtime`：固定声明 protocol identity 未认证、Agent Runtime 未连接、模型/工具调用为 0、仅接受手工 source metadata ingress、没有自动 dispatch。
- `GET /api/local/team/inbox?actor_id=...`：只返回该 protocol identity 当前仍有 Workspace/Channel/clearance 权限的 attention、work mark 和 sequence 元数据；不返回消息正文或附件。
- `POST /api/local/team/attention/items`：手工登记 opaque `source_ref`、目标 identity 与类型。服务端生成 Conversation sequence、固定 priority 和 open work mark，不接收消息内容。
- `POST /api/local/team/attention/items/{item_id}:claim`、`:release`、`:complete`：单 identity attention lease；到期/release 保留 open work mark，complete 只有在 item version、lease 与当前 read cursor 都匹配时才清除 mark。
- `POST /api/local/team/channels/{channel_id}/threads/{thread_id}:read`：写入当前 identity 已读到的 latest sequence；Handoff、submit 与 Gate 在同一事务中重验该 Thread 的 freshness。

所有写请求需要 `Idempotency-Key`。请求、响应与错误以 [`team-attention.schema.json`](../../specs/v1/team-attention.schema.json) 为准；它不是飞书/Slack/Email、Thread/DM 存储、自动通知、真实调度或身份认证。完整边界见 [Team Attention](TEAM_ATTENTION.md)。

## Team Session Continuity（ADR-0037，本机受限控制面）

- `GET /api/local/team/sessions/runtime`：固定声明 protocol identity / Agent Runtime / telemetry 未连接，模型/工具调用为零，且没有自动 Session rotation 或消息历史。
- `GET/POST /api/local/team/sessions`：只列出或创建当前 protocol identity 在已授权 Channel 上的 Team Session；同 identity/Channel 同时最多一个 active Session，可一次继承同 scope/identity 的 Handoff。
- `GET /api/local/team/sessions/{session_id}?actor_id=...`：读取一个 Session、由当前 Task/Gate/Attention/cursor 状态重新生成的无正文 Snapshot，以及可见的 inherited Handoff。
- `POST /api/local/team/sessions/{session_id}:handoff`：以 Session version CAS 生成由服务端派生的 Snapshot 并 retire 当前 Session；不修改/认领 Task、Attention、Gate 或 Run。

所有写请求需要 `Idempotency-Key`。请求、响应与错误以 [`team-session-continuity.schema.json`](../../specs/v1/team-session-continuity.schema.json) 为准；它不是 Provider/模型会话、聊天历史、自动 compaction/rotation、Daemon/Computer、真实身份认证或自动恢复。完整边界见 [Team Session Continuity](TEAM_SESSION_CONTINUITY.md)。

## Team Coordination（ADR-0033 + ADR-0035，本机受限控制面）

- `GET /api/local/team/runtime`：返回本地 Team control-plane 状态；固定为未连接 Agent Runtime、模型/外部工具调用为零。
- `GET /api/local/team/tasks?actor_id=...`、`POST /api/local/team/tasks`、`GET /api/local/team/tasks/{task_id}?actor_id=...`：读取或创建带冻结 requirements、scope、停止条件与 Gate 的协作 Task；新 `team-task@2` 要求 Workspace、Channel、clearance 和 role 边界。
- `POST /api/local/team/tasks/{task_id}:claim`：在 SQLite 事务中原子写入有期限的执行 lease。
- `POST /api/local/team/tasks/{task_id}/handoffs`：只有有效负责人可追加与 requirements/Gate digest、task version 绑定的 Handoff；当其 Thread 已有 attention sequence 时还必须携带新鲜的 read sequence。
- `POST /api/local/team/tasks/{task_id}:submit`：必须已有 Handoff 且没有开放 Child，才转为 `in_review`；存在 Thread attention 时阻断过期提交。
- `POST /api/local/team/tasks/{task_id}/gate-decisions`：只有预设 reviewer 可记录 `pass` / `reject` / `needs_human`；存在 Thread attention 时阻断过期审核；只有 pass 进入 `done`。
- `POST /api/local/team/tasks/{task_id}:close`：保存关闭人和原因，进入 `closed`；它不代表 Gate 通过。

所有写请求需要 `Idempotency-Key`，并以 `expected_task_version` 防止旧读取覆盖当前状态。请求、响应与错误约束以 [`team-coordination.schema.json`](../../specs/v1/team-coordination.schema.json) 为准；产品语义和非目标见 [Team Coordination](TEAM_COORDINATION.md)。它没有消息 Inbox、真实 Agent/Daemon/Computer 或生产身份认证；历史 `team-task@1` 不会被新 protocol identity 静默访问。

## Recovery Loop Guard（ADR-0034，本机受限控制面）

- `GET /api/local/recovery/runtime`：返回固定零执行边界；不会启动模型、工具、Checkpoint restore 或自动审批。
- `GET /api/local/recovery/cases?actor_id=...`、`POST /api/local/recovery/cases`：读取或创建绑定一个已 claim Team Task 的失败 Case。创建同时记录 Error Contract、失败点、根因**假设**、回滚 Checkpoint 和 Replan 起点，并冻结 Task/requirements/Gate/scope/输入/无工具权限摘要。
- `POST /api/local/recovery/cases/{case_id}/observations`：追加 failure 或 `verified_progress` Evidence；在连续失败时只写 Reminder，在 turn/时间/候选/重复 operation 或取消边界上硬停止。
- `POST /api/local/recovery/cases/{case_id}:try`：只生成 `proposed` 候选，不执行恢复。
- `POST /api/local/recovery/cases/{case_id}:confirm`：重新核对 Task、Checkpoint、固定权限、预算和输入摘要；成功后仍只进入 `confirmed_pending_handoff`。
- `POST /api/local/recovery/cases/{case_id}:cancel`：只追加 cancel audit 并终止候选；不作自动补偿。
- `POST /api/local/recovery/cases/{case_id}:link-handoff` 和 `:complete`：必须绑定同一 Team Task 的 Handoff，再由正常 Gate `pass` 结束 Case；重试/Confirm 成功绝不自动表示交付。

所有写请求需要 `Idempotency-Key` 和 `expected_case_version`。请求与响应以 [`recovery-loop-guard.schema.json`](../../specs/v1/recovery-loop-guard.schema.json) 为准，完整边界见 [Recovery Loop Guard](RECOVERY_LOOP_GUARD.md)。它不是开放式 Agent Replan、真实工具取消/恢复、身份授权或外部副作用控制 API。

## Research Agent Simulation（ADR-0023）

`POST /api/local/research-agents` 创建一个 Product Task 与父 Run；每个公司固定扇出财务、行业、风险三个 Child Run。请求必须带 `Idempotency-Key`，机器输入合同见 [`research-agent-runtime.schema.json`](../../specs/v1/research-agent-runtime.schema.json)。`GET /api/local/research-agents` 列出根 Run，`GET /api/local/research-agents/{run_id}` 返回冻结的 Agent / Skill / Tool 快照和可下载证据。

它是确定性的 Action → Observation → Final 模拟：每个 Child 仅用 `resource.inspect` 读取已分配 synthetic 资源，并且所有模型、Provider、网络和外部工具调用恒为零。完整边界和失败策略见 [Research Agent Runtime](RESEARCH_AGENT_RUNTIME.md)。

## Native Claude Research（ADR-0024，默认关闭）

- `GET /api/local/research-native/runtime`：只读返回 `claude-agent-sdk` / MCP 版本、插件摘要、模型/外部数据开关、允许域名、`claude-research-admission@1` 摘要及 blocker；不读取 Keychain、不启动 CLI、不发网络请求。档案不是认证系统，当前 `not_admitted` 会阻止环境变量误启用。
- `POST /api/local/research-native/documents?name=<report.pdf>`：仅接收 `application/pdf`、最大 15 MiB 的 Public 本地资料。它不解析、上传或发送资料。
- `POST /api/local/research-native`：须带 `Idempotency-Key`，请求遵循 [`claude-research-runtime.schema.json`](../../specs/v1/claude-research-runtime.schema.json) 的 `native_research_request`。只有 `approved_for_l3_probe` 准入档案及其 Provider/模型/费用/域名/endpoint/Keychain 引用/Public PDF/运维责任与运行/资料门禁均精确匹配时才创建 Product Task/Run；否则无副作用拒绝。
- `GET /api/local/research-native` 与 `GET /api/local/research-native/{run_id}`：返回父/子 Run、SDK 委派事件、Artifact 和来源 Evidence 摘要。

运行时父 Agent 只有原生 `Agent`，并必须委派 `financial`、`industry`、`risk` 三个 SDK Child Agent；Child 只可使用其固定插件 Skill 和 `research_sources` MCP 的资料工具。报告的 `source_id` 必须存在于同一 Run 的证据清单；无来源资料只能写为“未评估”。模型、资料外发、真实并发、取消和成本尚需 L3 Probe Evidence，详见 [Native Claude 投研运行时](CLAUDE_RESEARCH_RUNTIME.md)。

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
### Adaptive Chunk Retrieval（本地切片）

`build_parent_child_chunks` 输出带 `parent_id` 的结构化子证据；`weighted_rrf` 只融合 keyword/temporal/graph 候选；`slot_progress` / `should_stop_minimal` 依据关键槽位和 blocking gap 判断是否已达到最小充分证据。该模块不提供语义检索、外部端点或模型调用。

### Pi 离线管线的当前 HTTP 合同

HA-0067 给 `/api/local/pi/runtime` 和 `pi-contract-pipeline` 四个 POST 发布
源/静态/动态合同。`review-stream` 是确定性 `text/event-stream`，data JSON
依次是 preview、finding、done；done 不表示人工 Gate 通过或模型交付。
普通 POST key 上限 128，流因后缀上限 120；请求投影、Accept 子串检查、
两次收据非原子等现有边界见 `specs/testing/PI_PIPELINE_HTTP_CONTRACTS.md`。
security-check 的 allow 只是对调用方 policy 的评估，不授予执行权限；runtime
是档案投影，不是实时调用计数器。本项不包括 Pi Product Run 五个入口，
也不代表真实 Provider、部署或合同判断质量已经验收。

### Pi Product Run 当前合同（HA-0068）

`/api/local/pi-contract-review`的创建/列表/详情/events/Gate共五入口，源/静态/
动态合同复用Product Task/Run/Event/Artifact。事件为JSON页（最多500），
next_seq按返回页而非全Run最新序号推进，空页保留after_seq，范围为非负int64。
首次Gate在事务内核对waiting_approval并提交审计/终态；同key/body只读回放原收据，
不是新的执行许可。取消/超时后的迟到Adapter结果不再发布。仍是Faux-only、本机
可信用户纵切，非真实Provider/法律评测；详细验证见PI_PRODUCT_HTTP_CONTRACTS.md。
# Memory写回执（HA-0069）

Retain（201）、Source retract（200）和DELETE（200）现按memory-plane源Schema
公开local_http_memory_*响应，静态与动态都使用当前local_http_error信封。
Retain去重与首次写入、重复撤回与首次撤回的字段分支以Schema为准。
DELETE拒绝非空请求体（含分块），幂等键均1–128字符。
回放是历史收据；HA-0070在删除后使相关Retain/Entity/Relation内容回执失效，
旧key同请求返回409 MEMORY_RECEIPT_UNAVAILABLE，异请求仍409 CONFLICT。
启动会清理旧库孤儿内容收据，保留key/digest防止重试复活；删除/撤回收据不变。
不宣称磁盘/WAL/备份、FTS5影子表词项或其他独立副本擦除。
详见specs/testing/MEMORY_WRITE_CONTRACTS.md与specs/testing/MEMORY_RECEIPT_DELETION.md。

HA-0071：无既有FTS索引且启动创建精确缺模块时，keyword_index.error为固定
FTS5_UNAVAILABLE，M1写入/关键词Recall可用，M2 context返回503；索引或数据库
其他故障不再被误吞成M1扫描，返回无内部异常文本的500。恢复需修复环境后重启，
不在GET自动重建；readiness只描述上一次初始化。见ADR-0071。
