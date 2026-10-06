"""Explicit local deployment, refuses any existing8765 listener; backs up existing DB."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT).strip():
        raise SystemExit('Commit release before deployment')
    with socket.socket() as s:
        if s.connect_ex(('127.0.0.1',8765))==0:raise SystemExit('8765 occupied; refusing to stop unidentified service')
    private=Path('/Users/weberzhao/.local/share/harnessagent')
    private.mkdir(parents=True,exist_ok=True,mode=0o700)
    key=private/'support-master.key'
    if not key.exists():
        fd=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f:f.write(os.urandom(32));f.flush();os.fsync(f.fileno())
    db=Path('/Users/weberzhao/code/ai/harnessagent/.local/harness.db')
    db.parent.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=private/('support-backup-'+stamp+'.db')
    if db.exists():
        with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as src,sqlite3.connect(backup) as dest:
            src.backup(dest)
        backup.chmod(0o600)
    env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin','HOME':'/Users/weberzhao',
         'HARNESS_SUPPORT':'enabled','HARNESS_DB':str(db),'HARNESS_SUPPORT_MASTER_KEY_FILE':str(key),
         'HARNESS_SUPPORT_EMBEDDING_DIR':str(private/'support-embedding'),'HARNESS_AGENT_RUNTIME':'disabled'}
    subprocess.run(['launchctl','submit','-l','local.harnessagent.support-session','-o',str(private/'support.stdout.log'),
        '-e',str(private/'support.stderr.log'),'--','/usr/bin/env','-i',*[k+'='+v for k,v in env.items()],
        '/Users/weberzhao/code/ai/harnessagent/.venv/bin/python',str(ROOT/'deploy/run_support_local.py')],check=True)
    print(json.dumps({'submitted':True,'url':'http://127.0.0.1:8765/support','backup':str(backup) if backup.exists() else None}))


if __name__=='__main__':main()
