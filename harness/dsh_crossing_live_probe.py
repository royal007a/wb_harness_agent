"""Explicit post-deploy acceptance on 8876. --real spends quota on one synthetic case."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8876'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--release', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--real', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {'release': args.release, 'url': BASE + '/dsh', 'runs': [],
              'not_evidence': ['semantic_correctness', '132_deployment', 'OS_sandbox', 'cross_process_replay']}
    with httpx.Client(trust_env=False, timeout=15) as client, sync_playwright() as pw:
        def get(path):
            response = client.get(BASE + path)
            response.raise_for_status()
            return response.json()
        runtime = get('/api/local/dsh/runtime')
        assert runtime['release'] == args.release
        job = subprocess.check_output(['launchctl', 'list', 'local.harnessagent.dsh-session'], text=True)
        pid = int(re.search(r'"PID"\s*=\s*(\d+)', job).group(1))
        listeners = subprocess.check_output(['lsof', '-nP', '-iTCP:8876', '-sTCP:LISTEN', '-Fp'], text=True)
        assert {int(line[1:]) for line in listeners.splitlines() if line.startswith('p')} == {pid}
        report['pid'] = pid
        report['listener_matches_label'] = True
        cases = json.loads((ROOT / 'harness/eval/dsh_payment/cases.json').read_text())['cases']
        case = next(c for c in cases if c['id'] == 'pay-03')
        browser = pw.chromium.launch(headless=True, args=['--no-proxy-server'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1100})
        errors = []
        page.on('pageerror', lambda error: errors.append(type(error).__name__))
        for mode in ['integration_probe'] + (['real_provider'] if args.real else []):
            page.goto(BASE + '/dsh')
            expect(page.locator('#version')).to_contain_text(args.release)
            expect(page.locator('#mode')).to_have_value('integration_probe')
            page.locator('#mode').select_option(mode)
            page.locator('#template').select_option('payment_terms')
            page.locator('#objective').fill(case['objective'])
            page.locator('#document').fill(case['document'])
            page.locator('#timeout').fill('240')
            page.locator('#public-confirm').check()
            with page.expect_response(lambda response: response.request.method == 'POST'
                                      and response.url == BASE + '/api/local/dsh/runs') as response:
                page.locator('#start').click()
            created = response.value.json()
            ident = created['initial_run']['id']
            print(json.dumps({'mode': mode, 'run_id': ident, 'stage': 'started'}), flush=True)
            page.wait_for_function("() => /已完成|失败|已取消|已超时/.test(document.querySelector('#run-summary').textContent)",
                                   timeout=300000)
            detail = get('/api/local/dsh/runs/' + ident)
            summary = {'mode': mode, 'run_id': ident, 'status': detail['run']['status'],
                       'exit_reason': detail['run']['exit_reason'], 'budget': detail['budget']}
            report['runs'].append(summary)
            print(json.dumps(summary), flush=True)
            # Preserve failure metadata before asserting; never export document/model bodies.
            (args.out / 'live.json').write_text(json.dumps(report, indent=2) + '\n')
            assert detail['run']['status'] == 'succeeded', summary
            expect(page.locator('#findings')).to_be_visible()
            expect(page.locator('#findings-table tr')).to_have_count(4)
            expect(page.locator('#plan-steps li')).to_have_count(4)
            expect(page.locator('#result')).not_to_be_empty()
            events = get('/api/local/dsh/runs/' + ident + '/events')['items']
            crossings = [event['data'] for event in events if event['event_type'] == 'dsh.crossing']
            states = {}
            for row in crossings:
                key = (row['generation'], row['crossing_id'])
                states.setdefault(key, []).append(row['status'])
            completed = [row for row in crossings if row['status'] == 'completed']
            assert all(sequence in (['issued', 'in_flight', 'completed'], ['issued', 'failed'])
                       for sequence in states.values()), states
            success = next(event['data'] for event in events if event['event_type'] == 'run.succeeded')
            assert sum(row['kind'] == 'model' for row in completed) == detail['budget']['calls'] == success['model_calls']
            assert sum(row['kind'] == 'tool' for row in completed) == success['tool_calls']
            assert detail['budget']['reserved'] == 0
            summary['completed_crossings'] = len(completed)
            summary['artifact_hashes_verified'] = True
            for artifact in detail['artifacts']:
                response = client.get(BASE + '/api/v1/artifacts/' + artifact['id'] + '/content')
                response.raise_for_status()
                assert hashlib.sha256(response.content).hexdigest() == artifact['sha256']
                assert len(response.content) == artifact['size_bytes']
                if artifact['name'] == 'dsh-findings.json':
                    record = response.json()
                    summary['business_status'] = record['business_status']
                    summary['submission_number'] = record['submission_number']
            page.screenshot(path=str(args.out / (mode + '.png')), full_page=True)
        assert not errors, errors
        report['browser_page_errors'] = errors
        report['workspace_recovery'] = get('/api/local/dsh/runtime')['workspace_recovery']
        (args.out / 'live.json').write_text(json.dumps(report, indent=2) + '\n')
        browser.close()


if __name__ == '__main__':
    main()
