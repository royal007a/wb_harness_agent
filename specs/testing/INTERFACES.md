# HTTP / 页面 / 静态入口测试清单

由 `python -m harness.interface_inventory --write` 生成；这里登记范围，不宣称验收完成。

总计 180 个方法/路径组合；测试观测见 HA-0053 Evidence。

| 方法与路径 | 功能 | 处理器 | 来源 | OpenAPI |
|---|---|---|---|---|
| `DELETE /api/local/memory/sources/{source_id}` | memory | `memory_source_delete` | `backend/app.py:402` | 是 |
| `DELETE /api/local/support/agents/{agent_id}` | customer-support | `support_agent_delete` | `backend/app.py:257` | 是 |
| `DELETE /api/local/support/documents/{document_id}` | customer-support | `support_document_delete` | `backend/app.py:213` | 是 |
| `DELETE /api/local/support/knowledge/{kb_id}` | customer-support | `support_knowledge_delete` | `backend/app.py:201` | 是 |
| `DELETE /api/local/support/providers/{provider_id}` | customer-support | `support_provider_delete` | `backend/app.py:167` | 是 |
| `DELETE /api/local/support/sessions/{session_id}` | customer-support | `support_session_delete` | `backend/app.py:273` | 是 |
| `DELETE /api/local/support/workflows/{workflow_id}` | customer-support | `support_workflow_delete` | `backend/app.py:245` | 是 |
| `GET /` | web | `index` | `backend/app.py:1002` | 是 |
| `GET /agent-lab` | web | `agent_lab_page` | `backend/app.py:876` | 否 |
| `GET /agent-runtime` | web | `agent_runtime_page` | `backend/app.py:880` | 否 |
| `GET /api/local/agent-lab/agents` | agent-lab | `agent_lab_agents` | `backend/app.py:674` | 是 |
| `GET /api/local/agent-lab/models` | agent-lab | `agent_lab_models` | `backend/app.py:666` | 是 |
| `GET /api/local/agent-lab/providers` | agent-lab | `agent_lab_providers` | `backend/app.py:658` | 是 |
| `GET /api/local/agent-lab/runtime` | agent-lab | `agent_lab_runtime` | `backend/app.py:591` | 是 |
| `GET /api/local/agent-lab/sessions` | agent-lab | `agent_lab_sessions` | `backend/app.py:682` | 是 |
| `GET /api/local/agent-lab/sessions/{session_id}` | agent-lab | `agent_lab_session_detail` | `backend/app.py:690` | 是 |
| `GET /api/local/agent-runtime/agents` | agent-runtime | `agent_runtime_agents` | `backend/app.py:619` | 是 |
| `GET /api/local/agent-runtime/models` | agent-runtime | `agent_runtime_models` | `backend/app.py:611` | 是 |
| `GET /api/local/agent-runtime/providers` | agent-runtime | `agent_runtime_providers` | `backend/app.py:599` | 是 |
| `GET /api/local/agent-runtime/providers/{provider_id}/readiness` | agent-runtime | `agent_runtime_provider_readiness` | `backend/app.py:607` | 是 |
| `GET /api/local/agent-runtime/runtime` | agent-runtime | `agent_runtime_status` | `backend/app.py:595` | 是 |
| `GET /api/local/agent-runtime/sessions` | agent-runtime | `agent_runtime_sessions` | `backend/app.py:627` | 是 |
| `GET /api/local/agent-runtime/sessions/{session_id}` | agent-runtime | `agent_runtime_session_detail` | `backend/app.py:635` | 是 |
| `GET /api/local/connectors/baidu-netdisk` | baidu | `baidu_netdisk_status` | `backend/app.py:726` | 是 |
| `GET /api/local/connectors/baidu-netdisk/callback` | baidu | `baidu_netdisk_callback` | `backend/app.py:738` | 否 |
| `GET /api/local/external-skills/packages` | external-skills | `external_skill_packages` | `backend/app.py:325` | 是 |
| `GET /api/local/external-skills/runtime` | external-skills | `external_skill_runtime` | `backend/app.py:321` | 是 |
| `GET /api/local/memory/banks` | memory | `memory_banks` | `backend/app.py:348` | 是 |
| `GET /api/local/memory/banks/{bank_id}` | memory | `memory_bank_detail` | `backend/app.py:356` | 是 |
| `GET /api/local/memory/runtime` | memory | `memory_runtime` | `backend/app.py:344` | 是 |
| `GET /api/local/pi-contract-review` | pi | `pi_contract_review_list` | `backend/app.py:825` | 是 |
| `GET /api/local/pi-contract-review/{run_id}` | pi | `pi_contract_review_detail` | `backend/app.py:829` | 是 |
| `GET /api/local/pi-contract-review/{run_id}/events` | pi | `pi_contract_review_events` | `backend/app.py:833` | 是 |
| `GET /api/local/pi/runtime` | pi | `pi_runtime` | `backend/app.py:797` | 是 |
| `GET /api/local/recovery/cases` | recovery | `recovery_cases` | `backend/app.py:555` | 是 |
| `GET /api/local/recovery/cases/{case_id}` | recovery | `recovery_case_detail` | `backend/app.py:563` | 是 |
| `GET /api/local/recovery/runtime` | recovery | `recovery_runtime` | `backend/app.py:551` | 是 |
| `GET /api/local/research` | research | `research_list` | `backend/app.py:764` | 是 |
| `GET /api/local/research-agents` | research-agents | `research_agents_list` | `backend/app.py:782` | 是 |
| `GET /api/local/research-agents/{run_id}` | research-agents | `research_agents_detail` | `backend/app.py:788` | 是 |
| `GET /api/local/research-native` | research-native | `research_native_list` | `backend/app.py:812` | 是 |
| `GET /api/local/research-native/runtime` | research-native | `research_native_runtime` | `backend/app.py:792` | 是 |
| `GET /api/local/research-native/{run_id}` | research-native | `research_native_detail` | `backend/app.py:817` | 是 |
| `GET /api/local/research/{run_id}` | research | `research_detail` | `backend/app.py:770` | 是 |
| `GET /api/local/runs/{run_id}/restore` | replan | `restore_status` | `backend/app.py:974` | 是 |
| `GET /api/local/sample` | platform | `sample` | `backend/app.py:896` | 是 |
| `GET /api/local/support/agents` | customer-support | `support_agents` | `backend/app.py:181` | 是 |
| `GET /api/local/support/documents/{document_id}` | customer-support | `support_document_detail` | `backend/app.py:209` | 是 |
| `GET /api/local/support/knowledge` | customer-support | `support_knowledge_list` | `backend/app.py:185` | 是 |
| `GET /api/local/support/knowledge/{kb_id}` | customer-support | `support_knowledge_detail` | `backend/app.py:193` | 是 |
| `GET /api/local/support/providers` | customer-support | `support_providers` | `backend/app.py:151` | 是 |
| `GET /api/local/support/sessions` | customer-support | `support_sessions` | `backend/app.py:261` | 是 |
| `GET /api/local/support/sessions/{session_id}` | customer-support | `support_session_detail` | `backend/app.py:269` | 是 |
| `GET /api/local/support/status` | customer-support | `support_status` | `backend/app.py:147` | 是 |
| `GET /api/local/support/workflows` | customer-support | `support_workflow_list` | `backend/app.py:229` | 是 |
| `GET /api/local/support/workflows/{workflow_id}` | customer-support | `support_workflow_detail` | `backend/app.py:237` | 是 |
| `GET /api/local/support/workflows/{workflow_id}/runs` | customer-support | `support_workflow_runs` | `backend/app.py:249` | 是 |
| `GET /api/local/team/attention/runtime` | attention | `team_attention_runtime` | `backend/app.py:419` | 是 |
| `GET /api/local/team/channels/{channel_id}` | team | `team_channel_detail` | `backend/app.py:510` | 是 |
| `GET /api/local/team/foundation/runtime` | team | `team_foundation_runtime` | `backend/app.py:415` | 是 |
| `GET /api/local/team/inbox` | attention | `team_inbox` | `backend/app.py:445` | 是 |
| `GET /api/local/team/runtime` | team | `team_runtime` | `backend/app.py:411` | 是 |
| `GET /api/local/team/sessions` | continuity | `team_sessions` | `backend/app.py:427` | 是 |
| `GET /api/local/team/sessions/runtime` | continuity | `team_session_runtime` | `backend/app.py:423` | 是 |
| `GET /api/local/team/sessions/{session_id}` | continuity | `team_session_detail` | `backend/app.py:436` | 是 |
| `GET /api/local/team/tasks` | team | `team_tasks` | `backend/app.py:519` | 是 |
| `GET /api/local/team/tasks/{task_id}` | team | `team_task_detail` | `backend/app.py:527` | 是 |
| `GET /api/local/team/workspaces` | team | `team_workspaces` | `backend/app.py:474` | 是 |
| `GET /api/local/team/workspaces/{workspace_id}` | team | `team_workspace_detail` | `backend/app.py:483` | 是 |
| `GET /api/local/team/workspaces/{workspace_id}/agents` | team | `team_workspace_agents` | `backend/app.py:487` | 是 |
| `GET /api/local/team/workspaces/{workspace_id}/channels` | team | `team_workspace_channels` | `backend/app.py:501` | 是 |
| `GET /api/v1/artifacts/{artifact_id}/content` | product | `content` | `backend/app.py:994` | 是 |
| `GET /api/v1/engines` | platform | `engines` | `backend/app.py:295` | 是 |
| `GET /api/v1/frameworks` | platform | `frameworks` | `backend/app.py:308` | 是 |
| `GET /api/v1/health` | platform | `health` | `backend/app.py:136` | 是 |
| `GET /api/v1/readiness` | platform | `engine_readiness` | `backend/app.py:313` | 是 |
| `GET /api/v1/replans/{replan_id}` | replan | `replan_detail` | `backend/app.py:950` | 是 |
| `GET /api/v1/resources` | platform | `resources` | `backend/app.py:317` | 是 |
| `GET /api/v1/resources/{resource_id}` | platform | `resource` | `backend/app.py:892` | 是 |
| `GET /api/v1/runs/{run_id}` | product | `run` | `backend/app.py:938` | 是 |
| `GET /api/v1/runs/{run_id}/artifacts` | product | `artifact_list` | `backend/app.py:983` | 是 |
| `GET /api/v1/runs/{run_id}/events` | product | `events` | `backend/app.py:978` | 是 |
| `GET /api/v1/runs/{run_id}/replans` | product | `replan_list` | `backend/app.py:946` | 是 |
| `GET /api/v1/tasks` | product | `tasks` | `backend/app.py:923` | 是 |
| `GET /api/v1/tasks/{task_id}` | product | `task_detail` | `backend/app.py:929` | 是 |
| `GET /api/v1/tasks/{task_id}/artifacts` | product | `task_artifacts` | `backend/app.py:987` | 是 |
| `GET /connectors/baidu-netdisk` | web | `baidu_netdisk_page` | `backend/app.py:884` | 否 |
| `GET /docs` | web | `api_docs` | `backend/app.py:1006` | 否 |
| `GET /openapi.json` | web | `openapi` | `framework` | 否 |
| `GET /research` | web | `research_page` | `backend/app.py:774` | 否 |
| `GET /research-agents` | web | `research_agents_page` | `backend/app.py:872` | 否 |
| `GET /static/{path:path}` | web | `static` | `frontend/` | 否 |
| `GET /support` | customer-support | `support_page` | `backend/app.py:177` | 是 |
| `HEAD /openapi.json` | web | `openapi` | `framework` | 否 |
| `HEAD /static/{path:path}` | web | `static` | `frontend/` | 否 |
| `POST /api/local/agent-lab/agents` | agent-lab | `agent_lab_agent_create` | `backend/app.py:678` | 是 |
| `POST /api/local/agent-lab/models` | agent-lab | `agent_lab_model_create` | `backend/app.py:670` | 是 |
| `POST /api/local/agent-lab/providers` | agent-lab | `agent_lab_provider_create` | `backend/app.py:662` | 是 |
| `POST /api/local/agent-lab/sessions` | agent-lab | `agent_lab_session_create` | `backend/app.py:686` | 是 |
| `POST /api/local/agent-lab/sessions/{session_id}/messages` | agent-lab | `agent_lab_message_create` | `backend/app.py:694` | 是 |
| `POST /api/local/agent-runtime/agents` | agent-runtime | `agent_runtime_agent_create` | `backend/app.py:623` | 是 |
| `POST /api/local/agent-runtime/models` | agent-runtime | `agent_runtime_model_create` | `backend/app.py:615` | 是 |
| `POST /api/local/agent-runtime/providers` | agent-runtime | `agent_runtime_provider_create` | `backend/app.py:603` | 是 |
| `POST /api/local/agent-runtime/sessions` | agent-runtime | `agent_runtime_session_create` | `backend/app.py:631` | 是 |
| `POST /api/local/agent-runtime/sessions/{session_id}/messages` | agent-runtime | `agent_runtime_message_create` | `backend/app.py:639` | 是 |
| `POST /api/local/connectors/baidu-netdisk/authorization` | baidu | `baidu_netdisk_authorization` | `backend/app.py:730` | 是 |
| `POST /api/local/connectors/baidu-netdisk:disconnect` | baidu | `baidu_netdisk_disconnect` | `backend/app.py:746` | 是 |
| `POST /api/local/external-skills/packages` | external-skills | `external_skill_package_register` | `backend/app.py:329` | 是 |
| `POST /api/local/external-skills/packages/{package_id}:execute` | external-skills | `external_skill_execute` | `backend/app.py:338` | 是 |
| `POST /api/local/intents:interpret` | intent | `interpret_intent` | `backend/app.py:900` | 是 |
| `POST /api/local/memory/banks` | memory | `memory_bank_create` | `backend/app.py:352` | 是 |
| `POST /api/local/memory/banks/{bank_id}/entities` | memory | `memory_entity_create` | `backend/app.py:364` | 是 |
| `POST /api/local/memory/banks/{bank_id}/relations` | memory | `memory_relation_create` | `backend/app.py:368` | 是 |
| `POST /api/local/memory/banks/{bank_id}/retain` | memory | `memory_retain` | `backend/app.py:360` | 是 |
| `POST /api/local/memory/banks/{bank_id}:context` | memory | `memory_context` | `backend/app.py:376` | 是 |
| `POST /api/local/memory/banks/{bank_id}:fact-lineage` | memory | `memory_fact_lineage` | `backend/app.py:392` | 是 |
| `POST /api/local/memory/banks/{bank_id}:graph-recall` | memory | `memory_graph_recall` | `backend/app.py:384` | 是 |
| `POST /api/local/memory/banks/{bank_id}:recall` | memory | `memory_recall` | `backend/app.py:372` | 是 |
| `POST /api/local/memory/banks/{bank_id}:recall-details` | memory | `memory_recall_details` | `backend/app.py:380` | 是 |
| `POST /api/local/memory/banks/{bank_id}:resolve-entity` | memory | `memory_entity_resolve` | `backend/app.py:388` | 是 |
| `POST /api/local/memory/sources/{source_id}:retract` | memory | `memory_source_retract` | `backend/app.py:396` | 是 |
| `POST /api/local/pi-contract-pipeline/preview` | pi | `pi_contract_pipeline_preview` | `backend/app.py:841` | 是 |
| `POST /api/local/pi-contract-pipeline/review` | pi | `pi_contract_pipeline_review` | `backend/app.py:845` | 是 |
| `POST /api/local/pi-contract-pipeline/review-stream` | pi | `pi_contract_pipeline_review_stream` | `backend/app.py:853` | 是 |
| `POST /api/local/pi-contract-pipeline/security-check` | pi | `pi_contract_pipeline_security_check` | `backend/app.py:849` | 是 |
| `POST /api/local/pi-contract-review` | pi | `pi_contract_review_create` | `backend/app.py:821` | 是 |
| `POST /api/local/pi-contract-review/{run_id}:gate` | pi | `pi_contract_review_gate` | `backend/app.py:837` | 是 |
| `POST /api/local/recovery/cases` | recovery | `recovery_case_create` | `backend/app.py:559` | 是 |
| `POST /api/local/recovery/cases/{case_id}/observations` | recovery | `recovery_observation_create` | `backend/app.py:567` | 是 |
| `POST /api/local/recovery/cases/{case_id}:cancel` | recovery | `recovery_cancel` | `backend/app.py:579` | 是 |
| `POST /api/local/recovery/cases/{case_id}:complete` | recovery | `recovery_complete` | `backend/app.py:587` | 是 |
| `POST /api/local/recovery/cases/{case_id}:confirm` | recovery | `recovery_confirm` | `backend/app.py:575` | 是 |
| `POST /api/local/recovery/cases/{case_id}:link-handoff` | recovery | `recovery_link_handoff` | `backend/app.py:583` | 是 |
| `POST /api/local/recovery/cases/{case_id}:try` | recovery | `recovery_try` | `backend/app.py:571` | 是 |
| `POST /api/local/research` | research | `research_create` | `backend/app.py:760` | 是 |
| `POST /api/local/research-agents` | research-agents | `research_agents_create` | `backend/app.py:778` | 是 |
| `POST /api/local/research-native` | research-native | `research_native_create` | `backend/app.py:808` | 是 |
| `POST /api/local/research-native/documents` | research-native | `research_native_document` | `backend/app.py:802` | 是 |
| `POST /api/local/runs/{run_id}:restore` | replan | `restore` | `backend/app.py:970` | 是 |
| `POST /api/local/support/agents` | customer-support | `support_agent_create` | `backend/app.py:225` | 是 |
| `POST /api/local/support/exchanges/{exchange_id}/cancel` | customer-support | `support_exchange_cancel` | `backend/app.py:277` | 是 |
| `POST /api/local/support/knowledge` | customer-support | `support_knowledge_create` | `backend/app.py:189` | 是 |
| `POST /api/local/support/knowledge/{kb_id}/documents` | customer-support | `support_document_upload` | `backend/app.py:205` | 是 |
| `POST /api/local/support/knowledge/{kb_id}/search` | customer-support | `support_knowledge_search` | `backend/app.py:217` | 是 |
| `POST /api/local/support/providers` | customer-support | `support_provider_create` | `backend/app.py:155` | 是 |
| `POST /api/local/support/providers/{provider_id}/probe` | customer-support | `support_provider_probe` | `backend/app.py:171` | 是 |
| `POST /api/local/support/sessions` | customer-support | `support_session_create` | `backend/app.py:265` | 是 |
| `POST /api/local/support/sessions/{session_id}/messages` | customer-support | `support_message` | `backend/app.py:283` | 是 |
| `POST /api/local/support/workflows` | customer-support | `support_workflow_create` | `backend/app.py:233` | 是 |
| `POST /api/local/tasks` | product | `quick_task` | `backend/app.py:907` | 是 |
| `POST /api/local/team/attention/items` | attention | `team_attention_item_create` | `backend/app.py:449` | 是 |
| `POST /api/local/team/attention/items/{item_id}:claim` | attention | `team_attention_item_claim` | `backend/app.py:454` | 是 |
| `POST /api/local/team/attention/items/{item_id}:complete` | attention | `team_attention_item_complete` | `backend/app.py:464` | 是 |
| `POST /api/local/team/attention/items/{item_id}:release` | attention | `team_attention_item_release` | `backend/app.py:459` | 是 |
| `POST /api/local/team/channels/{channel_id}/memberships` | team | `team_channel_membership_grant` | `backend/app.py:514` | 是 |
| `POST /api/local/team/channels/{channel_id}/threads/{thread_id}:read` | team | `team_attention_read` | `backend/app.py:469` | 是 |
| `POST /api/local/team/sessions` | continuity | `team_session_create` | `backend/app.py:431` | 是 |
| `POST /api/local/team/sessions/{session_id}:handoff` | continuity | `team_session_handoff` | `backend/app.py:440` | 是 |
| `POST /api/local/team/tasks` | team | `team_task_create` | `backend/app.py:523` | 是 |
| `POST /api/local/team/tasks/{task_id}/gate-decisions` | team | `team_task_gate_decision` | `backend/app.py:547` | 是 |
| `POST /api/local/team/tasks/{task_id}/handoffs` | team | `team_task_handoff` | `backend/app.py:535` | 是 |
| `POST /api/local/team/tasks/{task_id}:claim` | team | `team_task_claim` | `backend/app.py:531` | 是 |
| `POST /api/local/team/tasks/{task_id}:close` | team | `team_task_close` | `backend/app.py:543` | 是 |
| `POST /api/local/team/tasks/{task_id}:submit` | team | `team_task_submit` | `backend/app.py:539` | 是 |
| `POST /api/local/team/workspaces` | team | `team_workspace_create` | `backend/app.py:478` | 是 |
| `POST /api/local/team/workspaces/{workspace_id}/agents` | team | `team_agent_create` | `backend/app.py:491` | 是 |
| `POST /api/local/team/workspaces/{workspace_id}/channels` | team | `team_channel_create` | `backend/app.py:505` | 是 |
| `POST /api/local/team/workspaces/{workspace_id}/memberships` | team | `team_workspace_membership_grant` | `backend/app.py:496` | 是 |
| `POST /api/v1/replans/{replan_id}:cancel` | replan | `replan_cancel` | `backend/app.py:962` | 是 |
| `POST /api/v1/replans/{replan_id}:confirm` | replan | `replan_confirm` | `backend/app.py:958` | 是 |
| `POST /api/v1/replans/{replan_id}:try` | replan | `replan_try` | `backend/app.py:954` | 是 |
| `POST /api/v1/resources` | platform | `upload` | `backend/app.py:888` | 是 |
| `POST /api/v1/runs/{run_id}/replans` | product | `replan_create` | `backend/app.py:942` | 是 |
| `POST /api/v1/runs/{run_id}:cancel` | product | `cancel` | `backend/app.py:966` | 是 |
| `POST /api/v1/tasks` | product | `task_create` | `backend/app.py:919` | 是 |
| `POST /api/v1/tasks/{task_id}/runs` | product | `rerun` | `backend/app.py:934` | 是 |
| `PUT /api/local/support/agents/{agent_id}` | customer-support | `support_agent_update` | `backend/app.py:253` | 是 |
| `PUT /api/local/support/knowledge/{kb_id}` | customer-support | `support_knowledge_update` | `backend/app.py:197` | 是 |
| `PUT /api/local/support/providers/{provider_id}` | customer-support | `support_provider_update` | `backend/app.py:160` | 是 |
| `PUT /api/local/support/workflows/{workflow_id}` | customer-support | `support_workflow_update` | `backend/app.py:241` | 是 |

## 功能验收口径（含非 HTTP）

### customer-support：课程智能客服平台

独立单管理员客服；实现与部署验收逐项登记，尚未整体完成

必须验证：密钥仅数据库密文且HTTP只写；后台探测频率/互斥/错误脱敏；会话、知识库、工作流、MCP闭环与真实验证。

规格：`specs/testing/CUSTOMER_SUPPORT.md`、`docs/decisions/ADR-0090-customer-support-platform.md`

测试入口：`tests/test_support_providers.py`

### platform：平台发现与资源

固定资源与能力元数据；readiness 不代表真实模型准入

必须验证：能力与 gate 一致；CSV/资源边界、摘要、恶意内容；无外部请求；读取内容/生命周期/HEAD的HTTP行为；入口命中不是完整验收；当前Product成功/错误/下载与静态动态响应契约实例一致；Product游标int64边界及响应约束负例/突变保护。

规格：`docs/harness/LOCAL_WORKBENCH.md`、`docs/harness/FRAMEWORK_INTEGRATION.md`、`specs/testing/READ_SURFACES.md`、`specs/testing/PRODUCT_HTTP_CONTRACTS.md`、`specs/testing/PRODUCT_CONTRACT_BOUNDARIES.md`

测试入口：`tests/test_workbench.py`、`tests/test_framework_catalog.py`、`tests/test_read_surfaces.py`、`tests/test_product_http_contracts.py`、`tests/test_product_contract_boundaries.py`

### product：Product Task/Run/Event/Artifact

固定 CSV Product 路径；完整模型 CodeAct 仍未准入

必须验证：不可变 Task/终态；权限预算快照；取消、超时、重启、事件序号；数值回算与产物下载；并发/幂等/队列；读取内容/生命周期/HEAD的HTTP行为；入口命中不是完整验收；当前Product成功/错误/下载与静态动态响应契约实例一致；Product游标int64边界及响应约束负例/突变保护。

规格：`docs/harness/CORE_CONTRACTS.md`、`docs/harness/P0_DATA_ANALYSIS.md`、`specs/testing/READ_SURFACES.md`、`specs/testing/PRODUCT_HTTP_CONTRACTS.md`、`specs/testing/PRODUCT_CONTRACT_BOUNDARIES.md`

测试入口：`tests/test_workbench.py`、`tests/test_product_http_contracts.py`、`tests/test_product_contract_boundaries.py`

### replan：Checkpoint / Try Confirm Cancel

只有固定统计 checkpoint 和白名单产物发布恢复，不是开放式 Replan

必须验证：版本/输入/权限/预算绑定；Try/Cancel 无执行；Confirm 去重；Gap 仅绑定恢复成功后解决；读取内容/生命周期/HEAD的HTTP行为；入口命中不是完整验收。

规格：`docs/harness/PLAN_REPLAN_CONTROL.md`、`specs/testing/READ_SURFACES.md`

测试入口：`tests/test_workbench.py`、`tests/test_execution_control.py`

### intent：Intent Contract 与拒识

规则预检；模型路由只有离线评测，不执行自然语言任意任务

必须验证：槽位与澄清；支持/拒识；固定评测、错路由反例；不创建 Task 或扩大权限。

规格：`docs/harness/INTENT_ROUTING.md`、`docs/harness/INTENT_MODEL_EVALUATION.md`

测试入口：`tests/test_intent.py`

### research：固定研究编排

最多 9 Child Run，固定函数与 synthetic 输入

必须验证：并发上限；父子权限/预算；部分失败、取消、整树重跑、重启；读取内容/生命周期/HEAD的HTTP行为；入口命中不是完整验收；Memory/Research读取静态动态源合同、退化状态与历史实例负例。

规格：`docs/harness/MULTI_AGENT.md`、`specs/testing/READ_SURFACES.md`、`specs/testing/MEMORY_RESEARCH_READ_CONTRACTS.md`

测试入口：`tests/test_research.py`、`tests/test_read_surfaces.py`、`tests/test_memory_research_read_contracts.py`

### research-agents：三角色投研契约模拟

Agent/Skill/Tool 模拟；零模型、零网络

必须验证：Skill 摘要与资源 scope；Action/Observation/Final；拒绝越权；父报告独立复算；已发布Schema归属、无覆盖、HTTP实例正反例；读取内容/生命周期/HEAD的HTTP行为；入口命中不是完整验收；Memory/Research读取静态动态源合同、退化状态与历史实例负例。

规格：`docs/harness/RESEARCH_AGENT_RUNTIME.md`、`specs/testing/OPENAPI_CONTRACTS.md`、`specs/testing/READ_SURFACES.md`、`specs/testing/MEMORY_RESEARCH_READ_CONTRACTS.md`

测试入口：`tests/test_research_agents.py`、`tests/test_openapi_contracts.py`、`tests/test_read_surfaces.py`、`tests/test_memory_research_read_contracts.py`

### research-native：Claude 原生投研准入与资料控制

代码/Mock/SDK 配置与拒绝路径；真实模型/资料外发未准入

必须验证：Provider/预算/端点/PDF 全绑定；默认零 CLI/Keychain/网络；来源证据、SSRF/字节上限；取消/部分失败/事件映射；读取内容/生命周期/HEAD的HTTP行为；入口命中不是完整验收；当前Product成功/错误/下载与静态动态响应契约实例一致；Product游标int64边界及响应约束负例/突变保护；Memory/Research读取静态动态源合同、退化状态与历史实例负例。

规格：`docs/harness/CLAUDE_RESEARCH_RUNTIME.md`、`specs/testing/READ_SURFACES.md`、`specs/testing/PRODUCT_HTTP_CONTRACTS.md`、`specs/testing/PRODUCT_CONTRACT_BOUNDARIES.md`、`specs/testing/MEMORY_RESEARCH_READ_CONTRACTS.md`

测试入口：`tests/test_claude_config.py`、`tests/test_claude_research_admission.py`、`tests/test_claude_research_runtime.py`、`tests/test_product_http_contracts.py`、`tests/test_product_contract_boundaries.py`、`tests/test_memory_research_read_contracts.py`

### external-skills：外部 Skill 沙箱

本机/SSH 管理员 ZIP JSON transform；未接 Product Run

必须验证：四入口源静态动态合同、坏ZIP解析及DB回滚历史收据；包 Schema/路径/摘要；代理拒绝；禁网非 root/只读/无凭证；输出/超时/并发/清理；两端真实容器；崩溃自动回收尚缺。

规格：`docs/harness/EXTERNAL_SKILL_RUNTIME.md`、`specs/testing/EXTERNAL_SKILL_HTTP_CONTRACTS.md`

测试入口：`tests/test_external_skills.py`、`tests/test_external_skill_http_contracts.py`

### memory：Memory M1/M2-A/M3 与语义准入

显式事实、FTS5/时间/两跳/精确实体；无自动聊天抽取/语义/Reflect

必须验证：Bank/time/source 过滤；supersede/retract/delete 传播；FTS 重建和详情；图/实体歧义与 lineage；语义 gate fail-closed；正文/跨 Bank 零泄漏；读取内容/生命周期/HEAD的HTTP行为；入口命中不是完整验收；Memory/Research读取静态动态源合同、退化状态与历史实例负例；Memory写回执、损坏准入档案、DELETE分块body及事务回滚；内容收据删除传播、旧键防复活、启动清理与原子回滚；FTS精确缺模块时M1可写，其他DB故障传播、重建与启动资源清理。

规格：`docs/harness/MEMORY_PLANE_M1.md`、`docs/harness/MEMORY_CONTEXT_M2A.md`、`docs/harness/MEMORY_GRAPH_M3A.md`、`docs/harness/MEMORY_ENTITY_CATALOG_M3B.md`、`specs/testing/READ_SURFACES.md`、`specs/testing/MEMORY_RESEARCH_READ_CONTRACTS.md`、`specs/testing/MEMORY_WRITE_CONTRACTS.md`、`specs/testing/MEMORY_RECEIPT_DELETION.md`、`specs/testing/MEMORY_FTS_AVAILABILITY.md`

测试入口：`tests/test_memory_plane.py`、`tests/test_memory_context.py`、`tests/test_memory_context_evaluation.py`、`tests/test_memory_graph.py`、`tests/test_memory_graph_evaluation.py`、`tests/test_memory_entity_catalog.py`、`tests/test_memory_fact_lineage.py`、`tests/test_memory_temporal_read_safety.py`、`tests/test_semantic_retrieval_admission.py`、`tests/test_read_surfaces.py`、`tests/test_memory_research_read_contracts.py`、`tests/test_memory_write_contracts.py`、`tests/test_memory_receipt_deletion.py`、`tests/test_memory_fts_availability.py`

### team：Team Foundation / Task Handoff Gate

metadata-only protocol actor，不是 HTTP 身份或自动委派

必须验证：请求主体先校验；仅明确不可见项过滤；意外故障和事务回滚；Workspace/Channel/clearance/role；claim lease/版本；父子依赖；Handoff 与 Gate digest；pass/reject/needs_human；HTTP创建/授予幂等与拒绝不变；Channel列表当前授权及重启后撤销；Foundation持久记录结构/枚举/SQL键损坏500，不伪装撤销；历史收据回放重验当前资格，拒绝或成功均不重执行业务。

规格：`specs/testing/TEAM_LIST_FAILURES.md`、`docs/harness/TEAM_FOUNDATION.md`、`docs/harness/TEAM_COORDINATION.md`、`specs/testing/TEAM_READ_VISIBILITY.md`、`specs/testing/TEAM_STATE_INTEGRITY.md`、`specs/testing/TEAM_REPLAY_AUTHORIZATION.md`

测试入口：`tests/test_team_list_failures.py`、`tests/test_team_foundation.py`、`tests/test_team_coordination.py`、`tests/test_team_read_visibility.py`、`tests/test_team_state_integrity.py`、`tests/test_team_replay_authorization.py`

### attention：Inbox / freshness / work mark

手工 metadata 输入，不唤醒模型

必须验证：请求主体先校验；仅明确不可见项过滤；意外故障和事务回滚；优先级/合并；lease/过期；已读与待办分离；freshness 原子拒绝；Foundation持久记录结构/枚举/SQL键损坏500，不伪装撤销；历史收据回放重验当前资格，拒绝或成功均不重执行业务。

规格：`specs/testing/TEAM_LIST_FAILURES.md`、`docs/harness/TEAM_ATTENTION.md`、`specs/testing/TEAM_STATE_INTEGRITY.md`、`specs/testing/TEAM_REPLAY_AUTHORIZATION.md`

测试入口：`tests/test_team_list_failures.py`、`tests/test_team_attention.py`、`tests/test_team_state_integrity.py`、`tests/test_team_replay_authorization.py`

### continuity：Team Session 交接

有界状态摘要；不是 Provider Session resume 或自动换代

必须验证：请求主体先校验；仅明确不可见项过滤；意外故障和事务回滚；scope/owner；单 active session；一次性继承/CAS；不复制正文、不改 Task/Attention；列表按主体/Channel/当前权限过滤且保留有权历史；Foundation持久记录结构/枚举/SQL键损坏500，不伪装撤销；历史收据回放重验当前资格，拒绝或成功均不重执行业务。

规格：`specs/testing/TEAM_LIST_FAILURES.md`、`docs/harness/TEAM_SESSION_CONTINUITY.md`、`specs/testing/TEAM_READ_VISIBILITY.md`、`specs/testing/TEAM_STATE_INTEGRITY.md`、`specs/testing/TEAM_REPLAY_AUTHORIZATION.md`

测试入口：`tests/test_team_list_failures.py`、`tests/test_team_session_continuity.py`、`tests/test_team_read_visibility.py`、`tests/test_team_state_integrity.py`、`tests/test_team_replay_authorization.py`

### recovery：Error Contract / Recovery Loop Guard

恢复决策旁路，Try/Confirm/Cancel 不执行工具

必须验证：请求主体先校验；仅明确不可见项过滤；意外故障和事务回滚；四个位置分离；Confirm 摘要；硬熔断/软提醒；取消与重复 operation；Handoff/Gate 后才能 resolved；Foundation持久记录结构/枚举/SQL键损坏500，不伪装撤销；历史收据回放重验当前资格，拒绝或成功均不重执行业务。

规格：`specs/testing/TEAM_LIST_FAILURES.md`、`docs/harness/RECOVERY_LOOP_GUARD.md`、`specs/testing/TEAM_STATE_INTEGRITY.md`、`specs/testing/TEAM_REPLAY_AUTHORIZATION.md`

测试入口：`tests/test_team_list_failures.py`、`tests/test_recovery_loop_guard.py`、`tests/test_team_state_integrity.py`、`tests/test_team_replay_authorization.py`

### agent-lab：Agent Lab

确定性演示回复，不调用 Provider

必须验证：Profile/Session/幂等；SSE delta/done；敏感字段拒绝；工具和模型调用恒零；已发布Schema归属、无覆盖、HTTP实例正反例。

规格：`docs/harness/LOCAL_WORKBENCH.md`、`specs/testing/OPENAPI_CONTRACTS.md`

测试入口：`tests/test_agent_lab.py`、`tests/test_openapi_contracts.py`

### agent-runtime：Provider/Agent/Session 文本 Runtime

默认关闭的文本 SSE；工具数 0，未接 Product Run

必须验证：Keychain 延迟解析；门禁/协议/上下文；流错误、取消、终态与并发；上游stop+DONE完整性与有界SSE解码；失败不伪造 assistant；持久 Exchange UI/重选刷新/过时响应/未提交预览；真实外发证据单列；已发布Schema归属、无覆盖、HTTP实例正反例。

规格：`docs/harness/AGENT_RUNTIME.md`、`specs/testing/AGENT_RUNTIME_LIFECYCLE.md`、`specs/testing/AGENT_RUNTIME_UI.md`、`specs/testing/PROVIDER_STREAM.md`、`specs/testing/OPENAPI_CONTRACTS.md`

测试入口：`tests/test_agent_runtime.py`、`tests/test_agent_runtime_lifecycle.py`、`tests/test_agent_runtime_ui.py`、`tests/test_provider_stream.py`、`tests/test_openapi_contracts.py`

### baidu：百度网盘 OAuth / 分享交接

OAuth 与本机 CLI 交接；网站接口没有通用分享下载

必须验证：state/回调/过期/断开；凭证引用不回显；刷新错误；分享 URL/提取码与人工登录边界。

规格：`docs/harness/BAIDU_NETDISK_CONNECTOR.md`

测试入口：`tests/test_baidu_netdisk.py`、`tests/test_baidu_netdisk_configuration.py`、`tests/test_baidu_netdisk_live_refresh.py`、`tests/test_baidu_share_handoff.py`

### pi：Pi 合同审查 Run / Pipeline / Admission

本仓库 Faux/确定性 Public PDF 路径；不是另一个 pi-contract-review 仓库

必须验证：JSONL/事件与版本；PDF/分页/风险/引用；高风险 Gate；敏感输入/注入；取消/有界输出/超时；真实 Provider 保持关闭；Pi离线管线五入口与分阶段SSE合同、错误和无执行边界；Pi Product五入口合同、Gate原子重放、迟到发布及连续事件分页。

规格：`docs/harness/PI_ADAPTER_DESIGN.md`、`specs/testing/PI_PIPELINE_HTTP_CONTRACTS.md`、`specs/testing/PI_PRODUCT_HTTP_CONTRACTS.md`

测试入口：`tests/test_pi_admission.py`、`tests/test_pi_contract_review_runtime.py`、`tests/test_pi_contract_review_adapter.py`、`tests/test_pi_contract_pipeline.py`、`tests/test_pi_security_guard.py`、`tests/test_pi_sidecar.py`、`tests/test_pi_contract_tui.py`、`tests/test_contract_risk_skill.py`、`tests/test_pi_pipeline_http_contracts.py`、`tests/test_pi_product_http_contracts.py`

### web：页面 / 静态文件 / OpenAPI

本机根路径及反向代理 /harness/；无新增身份系统

必须验证：静态资源与 CSP；API/下载/SSE 前缀；HTTP UUID fallback；动态/静态 OpenAPI 与真实契约一致；浏览器各页面；已发布Schema归属、无覆盖、HTTP实例正反例；读取内容/生命周期/HEAD的HTTP行为；入口命中不是完整验收；当前Product成功/错误/下载与静态动态响应契约实例一致；Product游标int64边界及响应约束负例/突变保护；Memory/Research读取静态动态源合同、退化状态与历史实例负例；Pi离线管线五入口与分阶段SSE合同、错误和无执行边界；Pi Product五入口合同、Gate原子重放、迟到发布及连续事件分页；Memory写回执、损坏准入档案、DELETE分块body及事务回滚。

规格：`docs/harness/LOCAL_WORKBENCH.md`、`docs/harness/API.md`、`specs/testing/OPENAPI_CONTRACTS.md`、`specs/testing/READ_SURFACES.md`、`specs/testing/PRODUCT_HTTP_CONTRACTS.md`、`specs/testing/PRODUCT_CONTRACT_BOUNDARIES.md`、`specs/testing/MEMORY_RESEARCH_READ_CONTRACTS.md`、`specs/testing/PI_PIPELINE_HTTP_CONTRACTS.md`、`specs/testing/PI_PRODUCT_HTTP_CONTRACTS.md`、`specs/testing/MEMORY_WRITE_CONTRACTS.md`

测试入口：`tests/test_frontend_paths.py`、`tests/test_workbench.py`、`tests/test_openapi_contracts.py`、`tests/test_read_surfaces.py`、`tests/test_product_http_contracts.py`、`tests/test_product_contract_boundaries.py`、`tests/test_memory_research_read_contracts.py`、`tests/test_pi_pipeline_http_contracts.py`、`tests/test_pi_product_http_contracts.py`、`tests/test_memory_write_contracts.py`

### retrieval：迭代检索/Agentic 契约/父子 Chunk

契约校验与确定性 Chunk/RRF helper；无生产迭代控制器或向量检索

必须验证：query_key/预算/目标依赖；无损 offset/CRLF/父子上限；路由准入/TopK/父聚合单调性；固定集、留出集与真实计算指标；拒绝未确认目标完成。

规格：`docs/harness/ITERATIVE_RETRIEVAL.md`、`docs/harness/AGENTIC_RAG_ADAPTATION.md`、`docs/harness/ADAPTIVE_CHUNK_RETRIEVAL.md`

测试入口：`tests/test_retrieval_state.py`、`tests/test_agentic_rag_state.py`、`tests/test_adaptive_retrieval.py`

### sandbox-probe：Smolagents / VM 探针及 Skill CLI

脚本模型开发探针，不注册为产品真实引擎

必须验证：隔离 executor；代码/输出/错误协议；取消超时/清理；CLI 参数/路径/manifest。

规格：`docs/harness/ENGINE_PROBES.md`、`docs/harness/SKILL_EXECUTION.md`、`docs/harness/TOOL_AND_SANDBOX.md`

测试入口：`tests/test_sandbox.py`、`tests/test_skill_script.py`

### operations：部署 / 备份 / 恢复 / 浏览器验收

launchd/systemd/nginx 双端；需要独立部署和浏览器证据

必须验证：实际 HARNESS_DB 备份；staging/运行环境保留；应用/镜像版本；代理认证/拒绝敏感路由；重启/回滚/全部页面浏览器；launchd 暂态有界重试与失败/回退健康证据；未准入功能仍关闭。

规格：`docs/harness/OPERATIONS.md`、`docs/harness/LOCAL_WORKBENCH.md`、`specs/testing/LOCAL_DEPLOYMENT_RECOVERY.md`、`AGENTS.md`

测试入口：`tests/test_frontend_paths.py`、`tests/test_workbench.py`、`tests/test_local_deployment.py`

### planned：未落地目标能力

Wiki 编译、真实身份、多租户、完整 CodeAct、外部 Skill→Product Run 桥尚未实现；不是测试通过项

必须验证：记录现状与目标差距；不把 Proposed 当实际功能；需独立契约、准入及运行证据。

规格：`docs/harness/LLM_WIKI.md`、`docs/harness/TEAM_IDENTITY_ADMISSION.md`、`docs/harness/P0_ACTIVATION_DECISION.md`

测试入口：尚无运行时，不作通过声明

