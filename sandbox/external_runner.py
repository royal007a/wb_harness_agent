"""Fixed external-Skill protocol runner. This file runs only in the container image."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path


MAX_OUTPUT_BYTES = 24 * 1024


class BoundedOutput(io.StringIO):
    def write(self, text):
        remaining = max(0, MAX_OUTPUT_BYTES - self.tell())
        super().write(str(text)[:remaining])
        return len(str(text))


def load_entrypoint():
    path = Path('/skill/entry.py')
    spec = importlib.util.spec_from_file_location('external_skill_entry', path)
    if not spec or not spec.loader:
        raise RuntimeError('invalid entrypoint')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    function = getattr(module, 'main', None)
    if not callable(function):
        raise RuntimeError('entrypoint must export main(payload)')
    return function


def run():
    raw = Path('/inputs/request.json').read_bytes()
    if len(raw) > 32 * 1024:
        raise RuntimeError('request too large')
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError('request must be object')
    logs = BoundedOutput()
    with contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
        output = load_entrypoint()(payload)
    if not isinstance(output, dict):
        raise RuntimeError('main must return object')
    encoded = json.dumps({'output': output}, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise RuntimeError('response too large')
    return encoded


try:
    print(run().decode())
except Exception:
    # Do not expose third-party stack traces or logs to the host/API surface.
    raise SystemExit(2)
