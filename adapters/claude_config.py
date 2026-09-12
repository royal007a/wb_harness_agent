"""Offline SDK type/serialization probe; no query(), client or CLI launch."""
from dataclasses import asdict
from importlib.metadata import version
import json

from backend.analysis import Problem


def configuration_probe():
    installed = version('claude-agent-sdk')
    if installed != '0.2.152':
        raise Problem('ADAPTER_VERSION_MISMATCH', '离线配置探针要求 claude-agent-sdk 0.2.152。')
    from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions
    prompts = {
        'financial-analyzer': ('财务专项', '仅基于分配的财务证据输出指标与来源；缺失口径时停止推断。'),
        'industry-collector': ('行业专项', '仅整理分配的行业资料，区分资料时间与当前时间，不虚构新闻。'),
        'risk-reviewer': ('风险专项', '输出已覆盖与缺失的证据，资料不足时标记未评估，不推断无风险。'),
    }
    definitions = {name: AgentDefinition(description=description, prompt=prompt,
                    tools=[], skills=[], model='inherit', maxTurns=3, mcpServers=[])
                   for name, (description, prompt) in prompts.items()}
    # No filesystem loading or third-party skills. This constructs Python data
    # only; it is NOT an approved runtime configuration or a safe OS sandbox.
    options = ClaudeAgentOptions(agents=definitions, tools=['Agent'], allowed_tools=[],
                                setting_sources=[], skills=[], plugins=[], mcp_servers={},
                                strict_mcp_config=True, max_turns=4, max_budget_usd=0,
                                env={'CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS':'1'})
    return {'sdk_version': installed, 'mode':'offline_configuration_only', 'real_model':False,
            'runtime_enabled':False, 'agents':{name:asdict(agent) for name,agent in definitions.items()},
            'parent':{'tools':options.tools,'allowed_tools':options.allowed_tools,
                      'setting_sources':options.setting_sources,'skills':options.skills,
                      'max_turns':options.max_turns, 'max_budget_usd':options.max_budget_usd},
            'limitations':['No subagent spawned','No skills loaded','No third-party model compatibility verified',
                           'Live use requires approved model, tool policy, environment isolation and event mapping']}


if __name__ == '__main__':
    print(json.dumps(configuration_probe(), ensure_ascii=False, indent=2))
