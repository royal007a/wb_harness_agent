import pytest

pytest.importorskip('claude_agent_sdk', reason='optional offline SDK configuration probe')

from adapters.claude_config import configuration_probe


def test_actual_sdk_agent_definition_fields():
    report = configuration_probe()
    assert report['sdk_version']=='0.2.152'
    assert not report['real_model'] and not report['runtime_enabled']
    assert len(report['agents'])==3
    for agent in report['agents'].values():
        assert agent['tools']==[] and agent['skills']==[] and agent['mcpServers']==[]
        assert agent['model']=='inherit' and agent['maxTurns']==3
    assert report['parent']['setting_sources']==[]


def test_configuration_does_not_share_mutable_definitions():
    first=configuration_probe();first['agents']['financial-analyzer']['tools'].append('Bash')
    assert configuration_probe()['agents']['financial-analyzer']['tools']==[]
