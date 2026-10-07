"""Isolated synthetic acceptance tests; never access a service, keychain or network."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from verify_receipt import Invalid, digest, load, validate_plan, verify


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        evidence = self.root / 'evidence.json'
        evidence.write_text('{"fixture":"synthetic observation, not a deployment"}')
        self.evidence = {'path': evidence.name, 'sha256': hashlib.sha256(evidence.read_bytes()).hexdigest()}
        self.plan = {'schema': 'deployment-plan@1', 'targets': [{
            'id': 'dsh', 'release': 'fixed-sha', 'data_path': None,
            'public_entry': {'url': 'https://example.test/dsh', 'tls': 'verified'},
            'checks': [
                {'id': 'release', 'required': True, 'expected': {'release': 'fixed-sha'}},
                {'id': 'identity', 'required': True, 'expected': {'service': 'dsh', 'identity_stable': True}},
                {'id': 'health', 'required': True, 'expected': {'state': 'ok'}},
                {'id': 'public_entry', 'required': True, 'expected': {'url': 'https://example.test/dsh', 'transport': 'direct', 'tls': 'verified'}},
                {'id': 'ui', 'required': True, 'expected': {'removed_count': 0}}
            ]}]}
        self.receipt = self.make_receipt()

    def make_receipt(self):
        return {'schema': 'deployment-receipt@1', 'plan_sha256': digest(self.plan), 'targets': [
            {'id': t['id'], 'deployment_status': 'deployed', 'checks': {
                c['id']: {'attempts': [{'status': 'pass', 'observed': copy.deepcopy(c['expected']), 'evidence': [self.evidence.copy()]}]}
                for c in t['checks']}} for t in self.plan['targets']]}

    def attempt(self, key):
        return self.receipt['targets'][0]['checks'][key]['attempts'][-1]

    def state(self):
        return verify(self.plan, self.receipt, self.root)['verification']

    def test_complete_contract(self):
        self.assertEqual(self.state(), 'verified')

    def test_wrong_running_release(self):
        self.attempt('release')['observed']['release'] = 'old-sha'
        self.assertEqual(self.state(), 'failed')

    def test_ui_http_success_does_not_prove_removed_entry(self):
        self.attempt('ui')['observed'] = {'http_status': 200, 'removed_count': 1}
        self.assertEqual(self.state(), 'failed')

    def test_health_does_not_cover_missing_public_entry(self):
        del self.receipt['targets'][0]['checks']['public_entry']
        self.assertEqual(self.state(), 'incomplete')

    def test_diagnostic_transport_never_substitutes_public(self):
        for mode in ['ssh_tunnel', 'ip_host', 'loopback', 'dns_override']:
            with self.subTest(mode=mode):
                self.attempt('public_entry')['observed']['transport'] = mode
                self.assertEqual(self.state(), 'failed')

    def test_changed_url_and_disabled_tls(self):
        for key, value in [('url', 'https://other.test/dsh'), ('tls', 'existing_exception')]:
            with self.subTest(field=key):
                self.receipt = self.make_receipt()
                self.attempt('public_entry')['observed'][key] = value
                self.assertEqual(self.state(), 'failed')

    def test_preaccepted_tls_exception_is_qualified(self):
        target = self.plan['targets'][0]
        target['public_entry'].update(tls='existing_exception', exception_reason='Previously approved lab self-signed certificate')
        target['checks'][3]['expected']['tls'] = 'existing_exception'
        self.receipt = self.make_receipt()
        self.assertEqual(self.state(), 'verified_with_exceptions')

    def test_plan_change_cannot_reuse_old_receipt(self):
        self.plan['targets'][0]['checks'][-1]['required'] = False
        with self.assertRaises(Invalid):
            self.state()

    def test_required_skipped_and_not_attempted(self):
        a = self.attempt('ui'); a.update(status='skipped', reason='Browser unavailable', evidence=[])
        self.assertEqual(self.state(), 'incomplete')
        self.receipt = self.make_receipt()
        self.receipt['targets'][0]['deployment_status'] = 'not_attempted'
        self.assertEqual(self.state(), 'incomplete')

    def test_optional_failure_is_visible(self):
        self.plan['targets'][0]['checks'][-1]['required'] = False
        self.receipt = self.make_receipt()
        self.attempt('ui').update(status='fail', reason='Optional viewport failed')
        result = verify(self.plan, self.receipt, self.root)
        self.assertEqual(result['verification'], 'verified_with_exceptions')
        self.assertTrue(result['targets'][0]['limitations'])

    def test_later_pass_keeps_prior_failure_count(self):
        attempts = self.receipt['targets'][0]['checks']['public_entry']['attempts']
        failure = copy.deepcopy(attempts[0]);failure.update(status='fail', reason='TLS reset')
        attempts.insert(0, failure)
        result = verify(self.plan, self.receipt, self.root)
        self.assertEqual(result['verification'], 'verified')
        self.assertEqual(result['targets'][0]['prior_failed_attempts'], 1)

    def test_multi_target_failure_not_averaged(self):
        other = copy.deepcopy(self.plan['targets'][0]); other['id'] = 'support'
        self.plan['targets'].append(other); self.receipt = self.make_receipt()
        self.attempt('public_entry').update(status='fail', reason='TLS reset')
        result = verify(self.plan, self.receipt, self.root)
        self.assertEqual(result['verification'], 'failed')
        self.assertEqual(result['targets'][1]['verification'], 'verified')

    def test_tamper_and_missing_evidence_rejected(self):
        (self.root / 'evidence.json').write_text('modified')
        with self.assertRaises(Invalid):self.state()
        (self.root / 'evidence.json').unlink()
        with self.assertRaises(Invalid):self.state()

    def test_path_escape_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as external:
            file = Path(external) / 'secret.txt';file.write_text('synthetic')
            (self.root / 'link').symlink_to(file)
            for path in ['../secret.txt', str(file), 'link']:
                with self.subTest(path=path):
                    self.attempt('release')['evidence'] = [{'path': path, 'sha256': hashlib.sha256(b'synthetic').hexdigest()}]
                    with self.assertRaises(Invalid):self.state()

    def test_truthy_numeric_not_boolean(self):
        self.attempt('identity')['observed']['identity_stable'] = 1
        self.assertEqual(self.state(), 'failed')

    def test_command_exit_code_not_inferred_from_log(self):
        self.plan['targets'][0]['checks'].append({'id': 'command', 'kind': 'command', 'required': True, 'expected': {'last_line': 'finished'}})
        for code in [None, False, 1, 0]:
            with self.subTest(code=code):
                self.receipt = self.make_receipt()
                if code is not None:self.attempt('command')['observed']['exit_code'] = code
                self.assertEqual(self.state(), 'verified' if type(code) is int and code == 0 else 'failed')

    def test_persistent_target_needs_bound_backup(self):
        target = self.plan['targets'][0];target['data_path'] = '/actual/live.db'
        with self.assertRaises(Invalid):validate_plan(self.plan)
        target['checks'] += [
            {'id': 'backup', 'required': True, 'expected': {'database': '/actual/live.db', 'integrity': 'ok'}},
            {'id': 'preservation', 'required': True, 'expected': {'unchanged': True}}
        ]
        self.receipt = self.make_receipt();self.assertEqual(self.state(), 'verified')
        self.attempt('backup')['observed']['database'] = '/wrong/default.db'
        self.assertEqual(self.state(), 'failed')

    def test_unknown_check_and_target_rejected(self):
        self.receipt['targets'][0]['checks']['unplanned'] = self.receipt['targets'][0]['checks']['health']
        with self.assertRaises(Invalid):self.state()
        self.receipt = self.make_receipt();self.receipt['targets'][0]['id'] = 'other'
        with self.assertRaises(Invalid):self.state()

    def test_json_duplicates_and_nonfinite_rejected(self):
        p = self.root / 'bad.json'
        for raw in ['{"x":1,"x":2}', '{"x":NaN}']:
            p.write_text(raw)
            with self.assertRaises(Invalid):load(p)

    def test_validation_does_not_execute_evidence(self):
        marker = self.root / 'must-not-exist'
        script = self.root / 'command.txt';script.write_text(f'touch {marker}')
        self.attempt('health')['evidence'] = [{'path': script.name, 'sha256': hashlib.sha256(script.read_bytes()).hexdigest()}]
        self.assertEqual(self.state(), 'verified');self.assertFalse(marker.exists())

    def test_cli_codes_and_invalid_input_no_traceback(self):
        p, r = self.root / 'plan.json', self.root / 'receipt.json'
        p.write_text(json.dumps(self.plan));r.write_text(json.dumps(self.receipt))
        command = [sys.executable, str(Path(__file__).with_name('verify_receipt.py')), str(p), str(r), '--evidence-root', str(self.root)]
        first = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0)
        self.attempt('ui')['observed']['removed_count'] = 1;r.write_text(json.dumps(self.receipt))
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)
        r.write_text('{}');last = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(last.returncode, 2);self.assertNotIn('Traceback', last.stderr)


if __name__ == '__main__':
    unittest.main()
