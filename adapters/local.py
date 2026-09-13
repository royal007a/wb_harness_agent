"""Deterministic baseline implementing the same explicit lifecycle boundary."""
import copy

from backend.analysis import Problem, analyze
from .contracts import AdapterResult, validate_result


class LocalAnalyticsAdapter:
    def describe(self):
        return {'adapter_id': 'local_analytics', 'adapter_version': '1.1.0', 'protocol_version': '1.0.0',
                'engine': 'engine_mock_analytics', 'capabilities': {
                    'actions.tool_call': True, 'artifacts.files': True, 'output.structured': True,
                    'control.cancel': {'supported': True, 'granularity': 'column_checkpoint'},
                    'state.checkpoint': {'supported': True, 'format': 'local_analytics_checkpoint@1',
                                         'boundary': 'after_resource_inspect', 'max_per_run': 1},
                    'state.restore': {'supported': True, 'source_statuses': ['failed', 'expired'],
                                      'cross_task': False, 'plan_changes': False},
                    'actions.code': False, 'agents.managed': False}}

    def start_run(self, request, emit, check):
        check()
        if request.run['effective_limits']['max_turns'] < 3:
            raise Problem('BUDGET_EXCEEDED', '固定分析需要 3 个工具步骤。')
        metrics = analyze(request.input_bytes, check)
        check()
        emit('tool.call.completed', {'tool': 'resource.inspect', 'implementation': 'deterministic'})
        return AdapterResult(metrics=metrics, usage={'model_calls': 0, 'cost_minor': 0})

    def checkpoint_run(self, request, result):
        """Return only the fixed, serializable post-inspection state; Service owns persistence."""
        validate_result(result)
        return {'state_version': 'local_analytics_checkpoint@1', 'metrics': copy.deepcopy(result.metrics)}

    def cancel_run(self, run_id):
        # Control-plane cancellation is checked at each bounded column step.
        return None

    def cleanup(self, run_id):
        return None

    def restore_run(self, request, checkpoint):
        if request.run['effective_limits']['max_turns'] < 2:
            raise Problem('BUDGET_EXCEEDED', '恢复后的固定发布路径至少需要 2 个工具步骤。')
        if not isinstance(checkpoint, dict) or checkpoint.get('state_version') != 'local_analytics_checkpoint@1':
            raise Problem('CHECKPOINT_STATE_INVALID', 'Checkpoint 状态格式不受当前固定分析器支持。')
        result = AdapterResult(metrics=checkpoint.get('metrics'), usage={'model_calls': 0, 'cost_minor': 0})
        validate_result(result)
        return result
