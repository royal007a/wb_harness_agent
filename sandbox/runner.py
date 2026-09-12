"""Runs ONLY inside the hardened VM container. JSON in/out; no host imports."""
import contextlib
import io
import json
import sys

LIMIT = 32768


class BoundedOutput(io.StringIO):
    def write(self, text):
        remaining = max(0, LIMIT - self.tell())
        super().write(text[:remaining])
        return len(text)


class FinalAnswer(BaseException):
    def __init__(self, value):
        self.value = value


def final_answer(value):
    raise FinalAnswer(value)


namespace = {'__name__': '__agent__', 'final_answer': final_answer}
transport = sys.stdout
for line in sys.stdin:
    logs = BoundedOutput()
    result = {'output': None, 'logs': '', 'is_final_answer': False, 'error': None}
    try:
        request = json.loads(line)
        with contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
            if request.get('operation') == 'variables':
                namespace.update(request['variables'])
            else:
                # This is deliberately unrestricted Python inside the OS sandbox,
                # never on the host. The outer container enforces the boundary.
                exec(compile(request['code'], '<agent>', 'exec'), namespace)
    except FinalAnswer as answer:
        result['output'] = answer.value
        result['is_final_answer'] = True
    except BaseException as error:
        result['error'] = type(error).__name__ + ': ' + str(error)[:2000]
    result['logs'] = logs.getvalue()
    try:
        encoded = json.dumps(result, ensure_ascii=True, allow_nan=False)
        if len(encoded) > 131072:
            raise ValueError('Result exceeds protocol limit')
    except (TypeError, ValueError):
        encoded = json.dumps({'output': None, 'logs': '', 'is_final_answer': False, 'error': 'Output must be bounded JSON'})
    transport.write(encoded + '\n')
    transport.flush()
