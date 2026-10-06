"""Independent oracle for the fixed synthetic script, not runtime/model quality."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from harness.dsh_payment_eval import score


def sample(claim='验收合格后30天内付款', unit='天'):
    label = {'id': 'probe', 'family': 'synthetic', 'true_value': 30, 'unit': unit,
             'exception_clause': None, 'exception_implicit': False, 'value_misstated_by_script': False}
    record = {'findings': {'term': {'status': 'supported', 'claim': claim},
                          'exception': {'status': 'unknown', 'quotes': []}},
              'candidates': {'exception': []}, 'platform_gaps': [], 'business_status': 'partial'}
    result = {'id': 'probe', 'status': 'succeeded', 'exit_reason': None, 'record': record,
              'model_calls': 3, 'coverage_warned': False}
    return result, label


@pytest.mark.parametrize('claim', [
    '验收合格后300天内付款', '验收合格后130天内付款', '验收合格后30个工作日内付款',
    '验收合格后30.5天内付款', '验收合格后-30天内付款', '验收合格后030天内付款',
    '验收合格后30天内付款，另付300元', '不应验收合格后30天内付款',
    '验收合格后三十天内付款', '验收合格后３０天内付款', '验收合格后30天内付款\n',
])
def test_numeric_and_unit_false_positives_rejected(claim):
    result, label = sample(claim)
    assert score([result], [label])[1]['correct_value_published'] == {'hit': 0, 'n': 1}


@pytest.mark.parametrize('value,unit', [(30, '天'), (300, '天'), (130, '个工作日'), (1, '天')])
def test_exact_script_values_pass(value, unit):
    result, label = sample(f'验收合格后{value}{unit}内付款', unit)
    label['true_value'] = value
    assert score([result], [label])[1]['correct_value_published'] == {'hit': 1, 'n': 1}


@pytest.mark.parametrize('broken', ['failed', 'missing_record', 'missing_candidates', 'wrong_candidates', 'unknown_term'])
def test_incomplete_run_is_not_a_positive_result(broken):
    result, label = sample()
    if broken == 'failed':
        result['status'] = 'failed'
    elif broken == 'missing_record':
        result['record'] = None
    elif broken == 'missing_candidates':
        result['record'].pop('candidates')
    elif broken == 'wrong_candidates':
        result['record']['candidates']['exception'] = None
    else:
        result['record']['findings']['term']['status'] = 'unknown'
    metrics = score([result], [label])[1]
    assert metrics['correct_value_published'] == {'hit': 0, 'n': 1}
    assert metrics['no_false_exception_candidate'] == {'hit': 0, 'n': 1}


@pytest.mark.parametrize('case', ['duplicate_result', 'duplicate_label', 'missing_result', 'missing_label', 'wrong_id', 'empty', 'empty_id'])
def test_denominator_cannot_drop_or_duplicate_cases(case):
    result, label = sample()
    results, labels = [result], [label]
    if case == 'duplicate_result': results *= 2
    elif case == 'duplicate_label': labels *= 2
    elif case == 'missing_result': results = []
    elif case == 'missing_label': labels = []
    elif case == 'wrong_id': result['id'] = 'different'
    elif case == 'empty': results, labels = [], []
    else: result['id'] = label['id'] = ''
    with pytest.raises(ValueError, match='case IDs'):
        score(results, labels)


@pytest.mark.parametrize('status,reason,artifact,hit', [
    ('failed', 'DSH_FINDINGS_INVALID', False, 1),
    ('failed', 'BUSINESS_TOKEN_BUDGET_EXHAUSTED', False, 0),
    ('failed', 'DSH_INITIALIZATION_TIMEOUT', False, 0),
    ('succeeded', 'DSH_FINDINGS_INVALID', False, 0),
    ('failed', 'DSH_FINDINGS_INVALID', True, 0),
    ('cancelled', 'DSH_FINDINGS_INVALID', False, 0),
])
def test_only_correct_rejection_without_publication_counts(status, reason, artifact, hit):
    result, label = sample()
    label['value_misstated_by_script'] = True
    result.update(status=status, exit_reason=reason)
    if not artifact: result['record'] = None
    assert score([result], [label])[1]['misstated_value_not_published'] == {'hit': hit, 'n': 1}


@pytest.mark.parametrize('implicit', [False, True])
def test_exception_metrics_require_success(implicit):
    result, label = sample()
    label.update(exception_clause='clause-4', exception_implicit=implicit)
    result['record']['candidates']['exception'] = ['clause-4']
    result['record']['findings']['exception'] = {'status': 'supported', 'quotes': [{'clause_id': 'clause-4'}]}
    name = 'implicit_exception_detected_by_platform_lexicon' if implicit else 'lexical_exception_surfaced'
    assert score([result], [label])[1][name] == {'hit': 1, 'n': 1}
    result['status'] = 'failed'
    assert score([result], [label])[1][name] == {'hit': 0, 'n': 1}


def test_all_fixture_labels_score_without_runtime_or_external_calls(monkeypatch):
    import socket
    from backend import dsh_findings
    def forbidden(*a, **kw): pytest.fail('scorer must not delegate its judgment or use network')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(dsh_findings, 'verify', forbidden)
    root = Path(__file__).resolve().parents[1] / 'harness/eval/dsh_payment'
    labels = json.loads((root / 'labels.json').read_text())['labels']
    cases = json.loads((root / 'cases.json').read_text())['cases']
    assert {x['id'] for x in cases} == {x['id'] for x in labels}
    results = []
    for label in labels:
        result, _ = sample(f"验收合格后{label['true_value']}{label['unit']}内付款")
        result['id'] = label['id']
        if label['value_misstated_by_script']:
            result.update(status='failed', exit_reason='DSH_FINDINGS_INVALID', record=None)
        elif label['exception_clause']:
            gold = label['exception_clause']
            result['record']['candidates']['exception'] = [gold]
            result['record']['findings']['exception'] = {'status': 'supported', 'quotes': [{'clause_id': gold}]}
        results.append(result)
    snapshot = deepcopy((results, labels))
    rows, metrics = score(results, labels)
    assert len(rows) == len(labels) == 21
    assert all(item['hit'] == item['n'] for item in metrics.values())
    assert (results, labels) == snapshot
    # This is a scorer-positive fixture, not evidence that the model found all implicit exceptions.
