"""Native Claude Agent SDK translation for the controlled research runtime.

This adapter deliberately owns no Product Task/Run storage and no source-policy
decision.  Its only jobs are to build a fixed SDK configuration, expose the
approved in-process MCP boundary, and reduce SDK messages to bounded audit
events.  The caller must decide whether an external model or source request is
authorized before calling :func:`stream_native_research`.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import shutil
from typing import Any, Protocol

from jsonschema import Draft202012Validator

from backend.analysis import Problem


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'specs/v1/claude-research-runtime.schema.json').read_text())
SDK_VERSION = '0.2.152'
RUNTIME_MODE = 'claude_native_research@1'
PLUGIN_ROOT = ROOT / 'plugins/research-skills'
PLUGIN_NAME = 'research-skills'
SOURCE_SERVER = 'research_sources'
SOURCE_TOOL_NAMES = {
    'financial': ('mcp__research_sources__financial_data', 'mcp__research_sources__pdf_extract', 'mcp__research_sources__web_fetch'),
    'industry': ('mcp__research_sources__web_search', 'mcp__research_sources__web_fetch'),
    'risk': ('mcp__research_sources__financial_data', 'mcp__research_sources__pdf_extract', 'mcp__research_sources__web_search', 'mcp__research_sources__web_fetch'),
}
SKILL_NAMES = {
    'financial': 'research-skills:financial-analysis',
    'industry': 'research-skills:industry-analysis',
    'risk': 'research-skills:risk-review',
}


class SourceGateway(Protocol):
    """A policy-enforcing implementation supplied by the backend layer."""

    async def search_news(self, query: str, limit: int) -> dict[str, Any]: ...
    async def fetch_url(self, url: str) -> dict[str, Any]: ...
    async def financial_data(self, stock_code: str, metric_group: str) -> dict[str, Any]: ...
    async def extract_pdf(self, resource_id: str, max_chars: int) -> dict[str, Any]: ...


@dataclass(frozen=True)
class NativeResearchConfig:
    """All non-secret state required to launch one fixed SDK query."""

    model: str | None
    runtime_enabled: bool
    external_data_enabled: bool
    allowed_domains: tuple[str, ...]
    cli_path: str
    max_turns: int
    max_cost_minor: int
    timeout_seconds: int
    plugin_root: Path = PLUGIN_ROOT

    @property
    def max_budget_usd(self) -> float:
        return self.max_cost_minor / 100


def _sha256(value: bytes | str) -> str:
    return sha256(value.encode('utf-8') if isinstance(value, str) else value).hexdigest()


def _bounded_text(value: Any, limit: int = 12000) -> str:
    if not isinstance(value, str):
        return ''
    return value[:limit]


def _version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def plugin_digest(root: Path = PLUGIN_ROOT) -> str:
    """Hash the full first-party plugin tree, including its manifest."""
    if not root.is_dir():
        raise Problem('RESEARCH_SKILL_PLUGIN_MISSING', '原生投研 Skill 插件目录不存在。', 409)
    pieces: list[bytes] = []
    for path in sorted(item for item in root.rglob('*') if item.is_file()):
        relative = path.relative_to(root).as_posix().encode('utf-8')
        pieces.extend((relative, b'\0', path.read_bytes(), b'\0'))
    if not pieces:
        raise Problem('RESEARCH_SKILL_PLUGIN_MISSING', '原生投研 Skill 插件为空。', 409)
    return _sha256(b''.join(pieces))


def runtime_status(env: dict[str, str] | None = None, *, cli_path: str | None = None) -> dict[str, Any]:
    """Read configuration only; never resolve credentials or make a request."""
    env = os.environ if env is None else env
    configured_cli = cli_path or env.get('HARNESS_CLAUDE_RESEARCH_CLI') or 'claude'
    model = env.get('HARNESS_CLAUDE_RESEARCH_MODEL') or None
    domains = tuple(sorted({part.strip().lower() for part in env.get('HARNESS_CLAUDE_RESEARCH_ALLOWED_DOMAINS', '').split(',') if part.strip()}))
    blockers: list[str] = []
    if _version('claude-agent-sdk') != SDK_VERSION:
        blockers.append('sdk_version_mismatch')
    if _version('mcp') is None:
        blockers.append('mcp_missing')
    if not shutil.which(configured_cli):
        blockers.append('cli_not_found')
    if not PLUGIN_ROOT.is_dir():
        blockers.append('skill_plugin_missing')
    if env.get('HARNESS_CLAUDE_RESEARCH_RUNTIME') != 'enabled':
        blockers.append('runtime_gate_disabled')
    if env.get('HARNESS_CLAUDE_RESEARCH_EXTERNAL_DATA') != 'enabled':
        blockers.append('external_data_gate_disabled')
    if not model:
        blockers.append('model_not_configured')
    if not domains:
        blockers.append('allowed_domains_not_configured')
    if not env.get('HARNESS_CLAUDE_RESEARCH_SEARCH_ENDPOINT'):
        blockers.append('search_source_not_configured')
    if not env.get('HARNESS_CLAUDE_RESEARCH_FINANCIAL_ENDPOINT'):
        blockers.append('financial_source_not_configured')
    return {
        'mode': RUNTIME_MODE,
        'sdk_version': _version('claude-agent-sdk') or 'missing',
        'mcp_version': _version('mcp') or 'missing',
        'cli_path': configured_cli,
        'model': model,
        'runtime_enabled': env.get('HARNESS_CLAUDE_RESEARCH_RUNTIME') == 'enabled',
        'external_data_enabled': env.get('HARNESS_CLAUDE_RESEARCH_EXTERNAL_DATA') == 'enabled',
        'plugin_sha256': plugin_digest() if PLUGIN_ROOT.is_dir() else '0' * 64,
        'allowed_domains': list(domains),
        'blockers': blockers,
    }


def validate_contract(name: str, value: dict[str, Any]) -> None:
    schema = {'$ref': '#/$defs/' + name, '$defs': CONTRACT['$defs']}
    errors = list(Draft202012Validator(schema).iter_errors(value))
    if errors:
        raise Problem('CLAUDE_RESEARCH_CONTRACT_INVALID', '原生投研对象不满足机器契约。', 409)


def configuration_from_request(request: dict[str, Any], env: dict[str, str] | None = None) -> NativeResearchConfig:
    """Combine a validated per-Run budget with non-secret deployment settings."""
    validate_contract('native_research_request', request)
    status = runtime_status(env)
    validate_contract('runtime_configuration', status)
    return NativeResearchConfig(
        model=status['model'], runtime_enabled=status['runtime_enabled'],
        external_data_enabled=status['external_data_enabled'], allowed_domains=tuple(status['allowed_domains']),
        cli_path=status['cli_path'], max_turns=12, max_cost_minor=request['max_cost_minor'],
        timeout_seconds=request['timeout_seconds'], plugin_root=PLUGIN_ROOT,
    )


def assert_ready(config: NativeResearchConfig, env: dict[str, str] | None = None) -> None:
    status = runtime_status(env, cli_path=config.cli_path)
    if status['blockers']:
        raise Problem('CLAUDE_RESEARCH_RUNTIME_BLOCKED', '原生投研运行时未获启动条件：' + ', '.join(status['blockers']), 409)
    if not config.model or not config.runtime_enabled or not config.external_data_enabled:
        raise Problem('CLAUDE_RESEARCH_RUNTIME_BLOCKED', '原生投研运行时配置不完整。', 409)
    if config.max_turns < 4 or config.max_cost_minor <= 0 or not 30 <= config.timeout_seconds <= 900:
        raise Problem('BUDGET_EXCEEDED', '原生投研 Run 的回合、费用或超时预算无效。', 422)


def _agent_definitions():
    from claude_agent_sdk import AgentDefinition
    prompts = {
        'financial': '你是财务专项子代理。只使用获准的 MCP 资料工具和指定 Skill；保留来源 ID、期间、单位与不确定性，不给投资建议。',
        'industry': '你是行业专项子代理。只使用获准的 MCP 资料工具和指定 Skill；事实必须附来源 ID 和时间，不给投资建议。',
        'risk': '你是风险专项子代理。只使用获准的 MCP 资料工具和指定 Skill；缺少资料必须写未评估，不能推断无风险或给投资建议。',
    }
    return {
        role: AgentDefinition(
            description={'financial': '财务报告与指标证据分析', 'industry': '行业新闻与趋势证据整理', 'risk': 'A 股风险证据覆盖审查'}[role],
            prompt=prompts[role], tools=list(SOURCE_TOOL_NAMES[role]), skills=[SKILL_NAMES[role]],
            # Background agents make the intended concurrency an SDK runtime
            # property instead of a thread-pool convention in our control
            # plane.  The L3 trace must still prove that all three actually
            # started and completed; this setting alone is not proof.
            model='inherit', mcpServers=[SOURCE_SERVER], maxTurns=4, background=True,
            effort='high', permissionMode='dontAsk',
        ) for role in ('financial', 'industry', 'risk')
    }


def create_source_server(gateway: SourceGateway):
    """Create only the four first-party, read-only SDK MCP tools for one Run."""
    from claude_agent_sdk import ToolAnnotations, create_sdk_mcp_server, tool

    annotations = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True, maxResultSizeChars=16000)

    @tool('web_search', 'Search an approved news source. Returns bounded source evidence, not arbitrary pages.', {'query': str, 'limit': int}, annotations=annotations)
    async def web_search(args):
        return _tool_result(await gateway.search_news(args['query'], args['limit']))

    @tool('web_fetch', 'Fetch an HTTPS URL that is within the approved source domains. Returns bounded source evidence.', {'url': str}, annotations=annotations)
    async def web_fetch(args):
        return _tool_result(await gateway.fetch_url(args['url']))

    @tool('financial_data', 'Read approved, time-stamped financial data for one A-share stock code and metric group.', {'stock_code': str, 'metric_group': str}, annotations=annotations)
    async def financial_data(args):
        return _tool_result(await gateway.financial_data(args['stock_code'], args['metric_group']))

    @tool('pdf_extract', 'Extract bounded text from the single registered financial-report PDF resource.', {'resource_id': str, 'max_chars': int}, annotations=annotations)
    async def pdf_extract(args):
        return _tool_result(await gateway.extract_pdf(args['resource_id'], args['max_chars']))

    return create_sdk_mcp_server(name=SOURCE_SERVER, version='1.0.0', tools=[web_search, web_fetch, financial_data, pdf_extract])


def _tool_result(value: dict[str, Any]) -> dict[str, Any]:
    """MCP only receives a bounded JSON proof; platform retains raw source data."""
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        return {'content': [{'type': 'text', 'text': 'SOURCE_TOOL_INVALID_RESULT'}], 'is_error': True}
    if len(encoded.encode()) > 16384:
        return {'content': [{'type': 'text', 'text': 'SOURCE_TOOL_RESULT_TOO_LARGE'}], 'is_error': True}
    return {'content': [{'type': 'text', 'text': encoded}]}


async def _deny_unexpected_tool(tool_name: str, _input: dict[str, Any], _context):
    """A final SDK-level deny path; handlers enforce policy a second time."""
    from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
    # `can_use_tool` is applied to a native SubAgent as well as its parent.
    # Parent `allowed_tools=['Agent']` keeps source tools out of the parent;
    # role-specific AgentDefinition tools provide the second, narrower check
    # for each Child.  Denying every MCP tool here would make the declared
    # Child source capabilities unusable in a live SDK run.
    if tool_name == 'Agent' or tool_name in {name for values in SOURCE_TOOL_NAMES.values() for name in values}:
        return PermissionResultAllow()
    return PermissionResultDeny(message='Only the fixed native research Agent and its declared MCP source tools are allowed.', interrupt=True)


def build_options(config: NativeResearchConfig, source_server):
    """Build actual SDK options; construction itself does not launch the CLI."""
    if _version('claude-agent-sdk') != SDK_VERSION:
        raise Problem('ADAPTER_VERSION_MISMATCH', '原生投研适配器要求 claude-agent-sdk 0.2.152。', 409)
    if not config.plugin_root.is_dir():
        raise Problem('RESEARCH_SKILL_PLUGIN_MISSING', '原生投研 Skill 插件不存在。', 409)
    from claude_agent_sdk import ClaudeAgentOptions
    return ClaudeAgentOptions(
        tools=['Agent'], allowed_tools=['Agent'],
        disallowed_tools=['Bash', 'Read', 'Write', 'Edit', 'Glob', 'Grep', 'WebFetch', 'WebSearch'],
        system_prompt=(
            '你是投研主控。必须在同一轮中以后台并发方式调用 financial、industry、risk 三个原生 SubAgent；'
            '只汇总它们带 source_id 的事实，明确冲突与未评估项。不得给投资建议、交易意见或价格预测。'
        ),
        mcp_servers={SOURCE_SERVER: source_server}, strict_mcp_config=True,
        permission_mode='dontAsk', can_use_tool=_deny_unexpected_tool,
        agents=_agent_definitions(), setting_sources=[], skills=[],
        plugins=[{'type': 'local', 'path': str(config.plugin_root)}],
        model=config.model, cli_path=config.cli_path, cwd=ROOT,
        max_turns=config.max_turns, max_budget_usd=config.max_budget_usd,
        include_partial_messages=False, include_hook_events=True, forward_subagent_text=True,
        env={'CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS': '1'},
    )


def options_snapshot(options) -> dict[str, Any]:
    """Non-secret evidence for tests and Product Run snapshots."""
    agents = {name: asdict(value) for name, value in (options.agents or {}).items()}
    return {
        'tools': list(options.tools or []), 'allowed_tools': list(options.allowed_tools),
        'disallowed_tools': list(options.disallowed_tools), 'strict_mcp_config': options.strict_mcp_config,
        'permission_mode': options.permission_mode, 'setting_sources': list(options.setting_sources or []),
        'skills': list(options.skills or []), 'plugin_paths': [item['path'] for item in options.plugins],
        'max_turns': options.max_turns, 'max_budget_usd': options.max_budget_usd,
        'agents': agents,
    }


def normalize_sdk_message(message: Any) -> list[dict[str, Any]]:
    """Map SDK message objects to bounded, secret-free platform-event payloads."""
    from claude_agent_sdk import AssistantMessage, RateLimitEvent, ResultMessage, SystemMessage, ToolResultBlock, ToolUseBlock, TextBlock
    output: list[dict[str, Any]] = []
    if isinstance(message, AssistantMessage):
        scope = 'child' if message.parent_tool_use_id else 'parent'
        for block in message.content:
            if isinstance(block, TextBlock):
                text = _bounded_text(block.text)
                output.append({'kind': 'assistant.text', 'agent_scope': scope, 'parent_tool_use_id': message.parent_tool_use_id,
                               'payload': {'text': text, 'sha256': _sha256(text), 'truncated': len(block.text) > len(text)}})
            elif isinstance(block, ToolUseBlock):
                payload = json.dumps(block.input, ensure_ascii=False, sort_keys=True, allow_nan=False)
                routing = block.input.get('subagent_type') if block.name == 'Agent' and isinstance(block.input, dict) else None
                output.append({'kind': 'assistant.tool_use', 'agent_scope': scope, 'parent_tool_use_id': message.parent_tool_use_id,
                               'payload': {'tool_use_id': block.id, 'tool': block.name, 'input_sha256': _sha256(payload),
                                           'input_bytes': len(payload.encode()), **({'subagent_type': routing} if routing in {'financial', 'industry', 'risk'} else {})}})
            elif isinstance(block, ToolResultBlock):
                serialized = json.dumps(block.content, ensure_ascii=False, sort_keys=True, default=str)
                output.append({'kind': 'assistant.tool_result', 'agent_scope': scope, 'parent_tool_use_id': message.parent_tool_use_id,
                               'payload': {'tool_use_id': block.tool_use_id, 'content_sha256': _sha256(serialized), 'content_bytes': len(serialized.encode()), 'is_error': bool(block.is_error)}})
    elif isinstance(message, ResultMessage):
        output.append({'kind': 'sdk.result', 'agent_scope': 'parent', 'parent_tool_use_id': None,
                       'payload': {'subtype': message.subtype, 'is_error': message.is_error, 'num_turns': message.num_turns,
                                   'duration_ms': message.duration_ms, 'duration_api_ms': message.duration_api_ms,
                                   'total_cost_usd': message.total_cost_usd, 'stop_reason': message.stop_reason,
                                   'usage': message.usage or {}, 'errors': list(message.errors or [])}})
    elif isinstance(message, SystemMessage):
        serialized = json.dumps(message.data, ensure_ascii=False, sort_keys=True, default=str)
        output.append({'kind': 'sdk.system', 'agent_scope': 'parent', 'parent_tool_use_id': None,
                       'payload': {'subtype': message.subtype, 'data_sha256': _sha256(serialized), 'data_bytes': len(serialized.encode())}})
    elif isinstance(message, RateLimitEvent):
        try:
            value = asdict(message)
        except TypeError:
            value = vars(message)
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        output.append({'kind': 'sdk.rate_limit', 'agent_scope': 'parent', 'parent_tool_use_id': None,
                       'payload': {'sha256': _sha256(serialized), 'bytes': len(serialized.encode())}})
    for event in output:
        validate_contract('sdk_event', event)
    return output


async def stream_native_research(prompt: str, config: NativeResearchConfig, gateway: SourceGateway,
                                 *, query_fn: Callable[..., AsyncIterator[Any]] | None = None) -> AsyncIterator[dict[str, Any]]:
    """Launch a real SDK query only after all gates pass, then yield audit events."""
    if not isinstance(prompt, str) or not 1 <= len(prompt) <= 12000:
        raise Problem('VALIDATION_ERROR', '原生投研提示词长度必须为 1–12000。', 422)
    assert_ready(config)
    options = build_options(config, create_source_server(gateway))
    if query_fn is None:
        from claude_agent_sdk import query as query_fn  # Lazy: default gate never starts SDK query.
    try:
        async with asyncio.timeout(config.timeout_seconds):
            async for message in query_fn(prompt=prompt, options=options):
                for event in normalize_sdk_message(message):
                    yield event
    except TimeoutError as exc:
        raise Problem('TIMEOUT', '原生投研 SDK 查询超过 Run 时间预算。', 504) from exc
