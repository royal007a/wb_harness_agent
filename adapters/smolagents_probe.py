"""Real SDK + VM executor integration probe, NEVER a production model route.

The response sequence is scripted. This verifies transport/loop behavior, not
language understanding, model credentials, token accounting or model quality.
"""
import json

from smolagents import CodeAgent, Model
from smolagents.models import ChatMessage
from smolagents.local_python_executor import CodeOutput, PythonExecutor

from backend.analysis import Problem
from backend.sandbox import DockerSandbox


class ProbeAbort(BaseException):
    """Bypass SDK recoverable-error retries for security/budget/cancel failures."""
    def __init__(self, problem):
        self.problem = problem


class SandboxExecutor(PythonExecutor):
    def __init__(self, sandbox):
        self.sandbox = sandbox
        self.final = None
        self.finished = False

    def send_tools(self, tools):
        if set(tools) != {'final_answer'}:
            raise ProbeAbort(Problem('FORBIDDEN', '探针不允许注入宿主工具。'))

    def send_variables(self, variables):
        if variables:
            raise ProbeAbort(Problem('FORBIDDEN', '探针不允许注入宿主变量。'))

    def __call__(self, code_action):
        try:
            result = self.sandbox.execute(code_action)
        except Problem as problem:
            raise ProbeAbort(problem) from None
        if result['error']:
            raise RuntimeError(result['error'])
        if result['is_final_answer']:
            self.finished, self.final = True, result['output']
        return CodeOutput(output=result['output'], logs=result['logs'],
                          is_final_answer=result['is_final_answer'])

    def cleanup(self):
        self.sandbox.cleanup()


class ScriptedProbeModel(Model):
    def __init__(self, responses, max_calls, check):
        super().__init__(model_id='scripted-probe-NOT-LLM')
        self.responses, self.max_calls, self.check = list(responses), max_calls, check
        self.calls = 0

    def generate(self, messages, **kwargs):
        try:
            self.check()
        except Problem as problem:
            raise ProbeAbort(problem) from None
        if self.calls >= self.max_calls or self.calls >= len(self.responses):
            raise ProbeAbort(Problem('BUDGET_EXCEEDED', '脚本模型调用上限。'))
        content = self.responses[self.calls]
        self.calls += 1
        return ChatMessage(role='assistant', content='<code>' + content + '</code>')


def run_probe(raw, responses, *, max_calls=3, check=lambda: None, step_timeout=5):
    if type(max_calls) is not int or not 1 <= max_calls <= 5:
        raise Problem('VALIDATION_ERROR', '探针调用上限必须为 1–5。')
    if not 1 <= len(responses) <= 5 or any(not isinstance(r, str) or len(r.encode()) > 16000 for r in responses):
        raise Problem('VALIDATION_ERROR', '探针脚本数量或长度超限。')
    events = []
    model = ScriptedProbeModel(responses, max_calls, check)
    try:
        with DockerSandbox(raw, check=check, emit=lambda kind, data: events.append({'type': kind, 'data': data}),
                           step_timeout=step_timeout) as sandbox:
            executor = SandboxExecutor(sandbox)
            agent = CodeAgent(tools=[], model=model, executor=executor,
                              additional_authorized_imports=['csv', 'json', 'math'],
                              max_steps=max_calls, verbosity_level=0,
                              max_print_outputs_length=4000, add_base_tools=False)
            agent.run('Read /inputs/data.csv and return the requested structured calculation.')
            # SDK max-step text fallback is NOT an accepted executable result.
            if not executor.finished:
                raise Problem('ADAPTER_PROTOCOL_ERROR', '没有沙箱 final_answer 结果。')
            json.dumps(executor.final, allow_nan=False)
            value = executor.final
    except ProbeAbort as aborted:
        raise aborted.problem from None
    return {'mode': 'scripted_probe', 'real_model': False, 'sdk_calls': model.calls,
            'model_calls': 0, 'output': value, 'events': events}
