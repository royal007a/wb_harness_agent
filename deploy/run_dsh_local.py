"""Private working directory/umask for the session-scoped DSH launchd job."""
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
os.chdir(root)
os.umask(0o077)
sys.path.insert(0, str(root))

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('backend.app:app', host='127.0.0.1', port=8876,
                workers=1, access_log=False, timeout_graceful_shutdown=10)
