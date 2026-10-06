"""HA-0114: read-only decision-path projection of a DSH Run (jikesummary Tracing 复盘决策路径).

Built only from persisted metadata events and whitelisted fields; it never reads
artifacts or documents and never writes. Turns are delimited by context assembly,
which precedes every model request.
"""
from __future__ import annotations

TRACE_VERSION = 'dsh-trace@1'
_TOOL = ('tool', 'call_number', 'clause_ids', 'new_evidence', 'repeated_action', 'latency_ms',
         'error_code', 'total_matches', 'truncated')
_CHECK = ('accepted', 'submission_number', 'error_codes', 'business_status', 'platform_gap_count')
_TERMINAL = {'run.succeeded', 'run.failed', 'run.cancelled', 'run.expired'}


def _pick(data, keys):
    return {k: data[k] for k in keys if k in data}


def project(events):
    turns, current, outcome, versions, plan = [], None, None, None, {}
    for item in events:
        kind, data = item['event_type'], item.get('data') or {}
        if kind == 'dsh.run.versions':
            versions = _pick(data, ('release', 'prompt_sha256', 'contract_sha256', 'validator_sha256', 'plan_version'))
        elif kind == 'dsh.context.assembled':
            current = {'turn': data.get('call_number'), 'sequence': item['sequence'],
                       'context': _pick(data, ('estimate_after', 'budget', 'stubbed_tool_results', 'messages')),
                       'model': None, 'actions': [], 'plan_after': None}
            turns.append(current)
        elif kind == 'dsh.model.completed' and current is not None:
            current['model'] = _pick(data, ('latency_ms', 'usage'))
        elif kind == 'dsh.tool.completed' and current is not None:
            current['actions'].append(dict(kind='tool', **_pick(data, _TOOL)))
        elif kind == 'dsh.findings.checked' and current is not None:
            current['actions'].append(dict(kind='findings', **_pick(data, _CHECK)))
        elif kind in ('dsh.plan.created', 'dsh.plan.step'):
            plan.update({s['step_id']: s['status'] for s in data.get('steps', [])})
            if current is not None:
                current['plan_after'] = dict(plan)
        elif kind == 'dsh.progress.stopped' and current is not None:
            current['stopped'] = _pick(data, ('reason', 'no_progress_turns', 'repeat_turns'))
        elif kind in _TERMINAL:
            outcome = dict(event=kind, sequence=item['sequence'],
                           **_pick(data, ('error_code', 'failed_step', 'failure_point', 'business_status',
                                          'plan_status', 'model_calls', 'tool_calls')))
    return {'trace_version': TRACE_VERSION, 'versions': versions, 'turns': turns, 'outcome': outcome,
            'note': '只含平台元数据；不含合同正文、模型文本或工具参数原文。'}
