"""Private targeted mutation loader. Never loaded in production/full suite."""
import os
from pathlib import Path


def pytest_sessionstart(session):
    from adapters import dsh
    changes = {
        'primary': ('if cleanup_failed and primary_error is None:', 'if cleanup_failed:'),
        'success': ('if cleanup_failed and primary_error is None:', 'if False:'),
        'lease': ('lambda: thread.join(timeout=2), owned.close)', 'lambda: thread.join(timeout=2))'),
        'escalate': ('if signal_denied:\n            return', 'if False:\n            return'),
        'pipe': ('for pipe in (process.stdin, process.stdout):', 'for pipe in (process.stdin,):'),
    }
    before, after = changes[os.environ['HA92_MUTATION']]
    source = Path(dsh.__file__).read_text()
    assert source.count(before) == 1
    exec(compile(source.replace(before, after), dsh.__file__, 'exec'), dsh.__dict__)
