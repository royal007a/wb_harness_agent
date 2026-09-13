"""Deterministic, no-model intent preflight for the local CSV workbench."""
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from .analysis import Problem


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'specs/v1/intent-contract.schema.json').read_text())
RULE_VERSION = 'rules@1'
INTENT_ID = 'local_csv_analysis'
ACTION_TERMS = ('分析', '统计', '汇总', '检查', '质量', '概览', '趋势', '计算', '生成报告',
                'analy', 'summar', 'inspect', 'profil', 'statistic')
DATA_TERMS = ('csv', '数据', '表格', '字段', '列', '行', '数值', '缺失', '销售', 'dataset', 'table')


def validate_contract(kind, value, *, status=422):
    schema = {'$ref': '#/$defs/' + kind, '$defs': CONTRACT['$defs']}
    errors = list(Draft202012Validator(schema).iter_errors(value))
    if errors:
        code = 'VALIDATION_ERROR' if status < 500 else 'INTENT_CONTRACT_INVALID'
        message = '意图预检请求无效。' if status < 500 else '意图预检结果不满足契约。'
        raise Problem(code, message, status)


def objective_digest(objective):
    return 'sha256:' + hashlib.sha256(objective.encode('utf-8')).hexdigest()


class IntentRouter:
    """A deliberately narrow rule router; it never creates Tasks or Runs."""

    def interpret(self, request, resource=None):
        validate_contract('intent_interpret_request', request)
        objective = request['objective']
        normalized = ' '.join(objective.split()).casefold()
        resource_id = resource['id'] if resource else None
        slots = [
            {'name': 'analysis_goal', 'kind': 'text', 'required': True,
             'status': 'satisfied' if normalized else 'missing', 'value_ref': None},
            {'name': 'resource_id', 'kind': 'resource_ref', 'required': True,
             'status': 'satisfied' if resource_id else 'missing', 'value_ref': resource_id},
        ]
        constraints = [
            {'id': 'registered_csv_resource', 'kind': 'hard',
             'status': 'passed' if resource_id else 'pending'},
            {'id': 'local_execution_only', 'kind': 'hard', 'status': 'passed'},
        ]
        result = {
            'contract_version': 'intent-contract@1',
            'decision': None,
            'intent': None,
            'objective_digest': objective_digest(objective),
            'objective_length': len(objective),
            'slots': slots,
            'missing_slots': [],
            'hard_constraints': constraints,
            'route': None,
            'clarification': None,
            'confidence': {'level': 'deterministic', 'basis': RULE_VERSION},
            'reason_codes': [],
            'model_calls': 0,
        }
        if not normalized:
            result.update(decision='rejected', reason_codes=['INTENT_EMPTY_OBJECTIVE'], missing_slots=['analysis_goal'])
        else:
            action_match = any(term in normalized for term in ACTION_TERMS)
            data_match = any(term in normalized for term in DATA_TERMS)
            if not action_match or not (data_match or resource_id):
                result.update(decision='rejected', reason_codes=['INTENT_UNSUPPORTED'])
            else:
                candidate = {'id': INTENT_ID, 'label': '本地 CSV 分析',
                             'rule_ids': ['INTENT_LOCAL_CSV_RULE']}
                result['intent'] = candidate
                if not resource_id:
                    result.update(
                        decision='clarification_required',
                        missing_slots=['resource_id'],
                        clarification={'question': '请先上传或选择一份 CSV 数据资源，再提交分析。',
                                       'slot_names': ['resource_id']},
                        reason_codes=['INTENT_LOCAL_CSV_RULE', 'INTENT_SLOT_RESOURCE_MISSING'],
                    )
                else:
                    result.update(
                        decision='ready',
                        route={'id': INTENT_ID, 'version': RULE_VERSION,
                               'engine_id': 'engine_mock_analytics',
                               'creation_mode': 'explicit_user_submit'},
                        reason_codes=['INTENT_LOCAL_CSV_RULE', 'INTENT_SLOT_RESOURCE_SATISFIED',
                                      'INTENT_ROUTE_LOCAL_ANALYTICS'],
                    )
        if result['decision'] == 'rejected' and result['intent'] is not None:
            raise Problem('INTENT_CONTRACT_INVALID', '拒识结果不能保留意图候选。', 500)
        validate_contract('intent_interpretation', result, status=500)
        return result
