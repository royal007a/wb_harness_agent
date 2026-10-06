"""Opt-in pytest plugin; isolated process only, no source-file mutation."""
import inspect
import os
import subprocess


def pytest_configure(config):
    import harness.dsh_payment_eval as target
    mode = os.environ['HA88_MODE']
    if mode == 'before':
        source = subprocess.check_output(['git', 'show', 'b63847a:harness/dsh_payment_eval.py'], text=True)
    else:
        source = inspect.getsource(target)
        old, new = {
            'M1': ("int(match[1]) == label['true_value']", "str(label['true_value']) in match[1]"),
            'M2': ("and match[2] == label['unit']", "and True"),
            'M3': ("result['status'] == 'succeeded' and _scorable_record(result['record'])", "_scorable_record(result['record'])"),
            'M4': ("if _case_ids(results) != _case_ids(labels):", "if False:"),
            'M5': ("and result['record'] is None", "and True"),
            'M6': ("valid and not candidates", "not candidates"),
        }[mode]
        assert source.count(old) == 1
        source = source.replace(old, new)
    exec(compile(source, target.__file__, 'exec'), target.__dict__)
