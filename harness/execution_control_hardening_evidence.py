"""Build HA-0016 Evidence for execution-control cross-record binding hardening."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'harness/evidence/HA-0016'
SCHEMA = ROOT / 'specs/v1/execution-control.schema.json'
FIXTURE = ROOT / 'fixtures/execution-control-evaluation-v1.json'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def junit_summary(path):
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == 'testsuite' else list(root.findall('testsuite'))
    return {name: sum(int(suite.attrib.get(name, '0')) for suite in suites)
            for name in ('tests', 'failures', 'errors', 'skipped')}


def is_valid(contract, kind, value):
    schema = {'$ref': '#/$defs/' + kind, '$defs': contract['$defs']}
    return Draft202012Validator(schema).is_valid(value)


def main():
    tests_path = EVIDENCE / 'all-tests.xml'
    evaluation_path = EVIDENCE / 'evaluation-results.json'
    summary = junit_summary(tests_path)
    evaluation = json.loads(evaluation_path.read_text())
    contract = json.loads(SCHEMA.read_text())
    sha = 'a' * 64
    stamp = '2026-09-13T12:00:00Z'
    unsupported_claim = {
        'contract_version': 'claim@1', 'id': 'clm_unbound', 'run_id': 'run_demo', 'kind': 'fact',
        'supporting_evidence_ids': [], 'contradicting_evidence_ids': [], 'reliability': 'verified',
        'status': 'supported', 'created_at': stamp,
    }
    unsafe_checkpoint = {
        'contract_version': 'checkpoint-projection@1', 'checkpoint_id': 'ckpt_demo', 'run_id': 'run_demo',
        'reliability': 'verified', 'checkpoint_digest': sha, 'state_digest': sha, 'evidence_digest': sha,
        'gap_digest': sha, 'adapter_digest': sha, 'resource_digest': sha, 'effective_permissions_digest': sha,
        'remaining_limits_digest': sha, 'adapter_restore_supported': False, 'restorable': True, 'created_at': stamp,
    }
    unbound_confirmation = {
        'contract_version': 'replan-attempt@1', 'id': 'rpl_demo', 'origin_run_id': 'run_demo',
        'origin_plan_revision_id': 'plan_demo', 'failure_event_id': 'evt_demo',
        'root_cause_evidence_ids': ['evi_demo'], 'root_cause_confidence': 'high',
        'rollback_checkpoint_id': 'ckpt_demo', 'replan_start_node_id': 'node_demo', 'invalidated_node_ids': [],
        'candidate_plan_revision_id': 'plan_next', 'candidate_plan_digest': sha, 'try_result_digest': None,
        'confirmation_binding_digest': None, 'confirmed_run_id': None, 'status': 'confirmed', 'created_at': stamp,
    }
    if (summary['tests'] < 141 or summary['failures'] or summary['errors']
            or evaluation.get('evaluation_version') != 'execution-control-evaluation@1'
            or evaluation.get('case_count') != 13 or evaluation.get('failed_case_ids') != []
            or is_valid(contract, 'claim', unsupported_claim)
            or is_valid(contract, 'checkpoint_projection', unsafe_checkpoint)
            or is_valid(contract, 'replan_attempt', unbound_confirmation)):
        raise SystemExit('execution-control hardening evidence does not satisfy acceptance checks')
    artifacts = ('all-tests.xml', 'evaluation-results.json', 'acceptance.md')
    manifest = {
        'task': 'HA-0016',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'status': 'passed',
        'scope': 'offline execution-control contract hardening only',
        'model_calls_by_harness': 0,
        'product_run_created_or_restored': False,
        'runtime_replan_api_exposed': False,
        'test_summary': summary,
        'fixture': {'sha256': sha256(FIXTURE), 'case_count': 13, 'classification': 'synthetic_deidentified'},
        'contract_sha256': sha256(SCHEMA),
        'rejected_contract_states': ['supported_claim_without_evidence', 'restorable_checkpoint_without_restore', 'confirmed_replan_without_binding'],
        'artifacts': {name: {'sha256': sha256(EVIDENCE / name)} for name in artifacts},
    }
    (EVIDENCE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'task': manifest['task'], 'status': manifest['status'], 'test_summary': summary}, ensure_ascii=False))


if __name__ == '__main__':
    main()
