"""Explicit, read-only framework selection metadata.

This is a catalog, not a router.  It never imports or starts an external
runtime and it cannot grant model, network, tool, or credential access.
"""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'specs/v1/framework-catalog.schema.json').read_text())


CATALOG = {
    'schema_version': 'framework-catalog@1',
    'items': [
        {
            'id': 'pi', 'name': 'Pi', 'language': 'typescript', 'role': 'agent_runtime',
            'abstraction': 'loop_first', 'status': 'available_offline',
            'adapter_id': 'engine_pi_contract_review_offline', 'external_calls': 0,
            'control_plane': 'harnessagent',
            'selection_rule': '选择 TypeScript、源码可审计的 Agent Loop；真实 Provider 仍需独立准入。',
            'capabilities': ['agent_loop', 'event_stream', 'provider_abstraction', 'human_gate'],
        },
        {
            'id': 'claude_agent_sdk', 'name': 'Claude Agent SDK', 'language': 'python',
            'role': 'agent_sdk', 'abstraction': 'loop_first', 'status': 'blocked',
            'adapter_id': 'engine_claude_research_native', 'external_calls': 0,
            'control_plane': 'harnessagent',
            'selection_rule': '选择 Claude 原生 Skills/SubAgent/Hook 能力；必须先满足 L3 Provider、资料源、预算和审计准入。',
            'capabilities': ['skills', 'subagents', 'hooks', 'mcp'],
        },
        {
            'id': 'langchain', 'name': 'LangChain', 'language': 'typescript_and_python',
            'role': 'component_ecosystem', 'abstraction': 'component_first', 'status': 'reference_only',
            'adapter_id': None, 'external_calls': 0, 'control_plane': 'harnessagent',
            'selection_rule': '只作为模型、工具、检索和集成组件；不直接成为 Harness Run 的隐式执行引擎。',
            'capabilities': ['model_integrations', 'tool_integrations', 'retrieval', 'rag'],
        },
        {
            'id': 'langgraph', 'name': 'LangGraph', 'language': 'typescript_and_python',
            'role': 'orchestration_runtime', 'abstraction': 'state_first', 'status': 'planned',
            'adapter_id': None, 'external_calls': 0, 'control_plane': 'harnessagent',
            'selection_rule': '仅当业务需要显式状态图、分支并行、暂停恢复或人机节点时引入；不替换平台 Task/Run。',
            'capabilities': ['state_graph', 'checkpoint', 'durable_execution', 'human_in_loop'],
        },
    ],
}


def catalog() -> dict:
    """Return a defensive copy after validating the checked-in contract."""
    errors = list(Draft202012Validator(SCHEMA).iter_errors(CATALOG))
    if errors:
        raise RuntimeError('FRAMEWORK_CATALOG_INVALID')
    return json.loads(json.dumps(CATALOG))
