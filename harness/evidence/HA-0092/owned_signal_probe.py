"""Only signal freshly spawned local children; no recovered PID or Provider."""
import collections
import os
import signal
import subprocess
import time

counts = collections.Counter()
for _ in range(20):
    child = subprocess.Popen(['/usr/bin/true'], start_new_session=True)
    time.sleep(.002)
    try:
        os.killpg(child.pid, signal.SIGTERM)
        outcome = 'signal_ok'
    except ProcessLookupError:
        outcome = 'ESRCH'
    except PermissionError:
        outcome = 'EPERM'
    finally:
        code = child.wait(timeout=3)
    counts[(outcome, code)] += 1
print(sorted((outcome, code, count) for (outcome, code), count in counts.items()))
