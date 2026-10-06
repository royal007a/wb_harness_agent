"""Separate local8765 customer support process; no inherited credential environment."""
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0,str(ROOT))
os.environ['HARNESS_RELEASE_COMMIT']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
import uvicorn
uvicorn.run('backend.app:app',host='127.0.0.1',port=8765,workers=1,access_log=False,
            timeout_graceful_shutdown=10)
