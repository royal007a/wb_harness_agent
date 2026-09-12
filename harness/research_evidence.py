"""Capture local deployment evidence after tests and browser acceptance."""
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
import urllib.request
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.claude_config import configuration_probe


def get(path):
    with urllib.request.urlopen('http://127.0.0.1:8765'+path,timeout=10) as response:
        return json.load(response)


def main():
    directory=ROOT/'harness/evidence/HA-0009'
    suite=ET.parse(directory/'all-tests.xml').getroot().find('testsuite')
    tests={key:int(suite.attrib[key]) for key in ('tests','failures','errors','skipped')}
    browser=json.loads((directory/'browser.json').read_text())
    baseline=json.loads((directory/'baseline/browser.json').read_text())
    assert tests['tests']>=88 and not any(tests[k] for k in ('failures','errors','skipped'))
    assert not browser['errors'] and not baseline['errors']
    root=get('/api/local/research')['items'][0]
    detail=get('/api/local/research/'+root['id'])
    assert root['status']=='succeeded' and not detail['real_model']
    for item in detail['children']:
        assert item['run']['parent_run_id']==root['id']
        for artifact in item['artifacts']:
            with urllib.request.urlopen('http://127.0.0.1:8765/api/v1/artifacts/'+artifact['id']+'/content',timeout=10) as response:
                raw=response.read()
            assert hashlib.sha256(raw).hexdigest()==artifact['sha256']
    config=configuration_probe()
    (directory/'claude-configuration.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
    paths=['backend/research.py','adapters/research_demo.py','adapters/claude_config.py',
           'specs/v1/research-request.schema.json','frontend/research.js']
    report={'checked_at':datetime.now(timezone.utc).isoformat(), 'status':'passed',
            'mode':'local_fixed_function_orchestration','real_model':False,'tests':tests,
            'browser_checks':len(browser['checks']),'baseline_browser_checks':len(baseline['checks']),
            'health':get('/api/v1/health'),'sample_root_run_id':root['id'],
            'sample_children':len(detail['children']),
            'sdk_versions':{name:version(name) for name in ('claude-agent-sdk','smolagents','mcp')},
            'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
            'limitations':['synthetic company fixtures','no Claude query or subagent execution',
                           'no financial/news source retrieval','thread context separation is not OS isolation']}
    (directory/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    main()
