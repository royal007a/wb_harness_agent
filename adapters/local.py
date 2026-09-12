"""Deterministic baseline implementing the same explicit lifecycle boundary."""
from backend.analysis import Problem, analyze
from .contracts import AdapterResult


class LocalAnalyticsAdapter:
    def describe(self):
        return {'adapter_id': 'local_analytics', 'adapter_version': '1.0.0', 'protocol_version': '1.0.0',
                'engine': 'engine_mock_analytics', 'capabilities': {
                    'actions.tool_call': True, 'artifacts.files': True, 'output.structured': True,
                    'control.cancel': {'supported': True, 'granularity': 'column_checkpoint'},
                    'state.restore': False, 'actions.code': False, 'agents.managed': False}}

    def start_run(self, request, emit, check):
        check()
        if request.run['effective_limits']['max_turns'] < 3:
            raise Problem('BUDGET_EXCEEDED', '固定分析需要 3 个工具步骤。')
        metrics = analyze(request.input_bytes, check)
        check()
        emit('tool.call.completed', {'tool': 'resource.inspect', 'implementation': 'deterministic'})
        return AdapterResult(metrics=metrics, usage={'model_calls': 0, 'cost_minor': 0})

    def cancel_run(self, run_id):
        # Control-plane cancellation is checked at each bounded column step.
        return None

    def cleanup(self, run_id):
        return None

    def restore_run(self, request, checkpoint):
        raise Problem('CHECKPOINT_INCOMPATIBLE', '固定分析器没有解释器检查点，请创建新 Run。')
