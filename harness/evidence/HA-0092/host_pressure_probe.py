"""Read-only machine counters, no process argv/environment or application data."""
import json
import re
import subprocess
import time

samples = []
for _ in range(6):
    began = time.monotonic()
    output = subprocess.run(['/usr/bin/vm_stat'], capture_output=True, text=True, check=True).stdout
    values = {}
    for line in output.splitlines():
        match = re.match(r'([^:]+):\s+(\d+)\.', line)
        if match:
            values[match.group(1)] = int(match.group(2))
    samples.append({'at':began, 'command_seconds':time.monotonic()-began,
                    'values':values})
    time.sleep(1)
elapsed = samples[-1]['at']-samples[0]['at']
keys = ['Pageins', 'Pageouts', 'Swapins', 'Swapouts', 'Compressions', 'Decompressions']
print(json.dumps({'samples':samples, 'elapsed_seconds':elapsed,
                 'page_size_bytes':16384,
                 'delta': {key:samples[-1]['values'][key]-samples[0]['values'][key] for key in keys}}, indent=2))
