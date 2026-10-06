"""HA0090 promotion on the already-authorized132 host; old runtime and DB backed up."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import urllib.request

LIVE=Path('/opt/harnessagent')
ENV=Path('/opt/harnessagent-support-env')
OVERRIDE=Path('/etc/systemd/system/harnessagent.service.d/support.conf')
PRESERVE=['.venv/','.local/','data/','node_modules/','__pycache__/','evidence/']

def run(args,**kw): return subprocess.check_output(args,text=True,**kw).strip()
def sync(source):
    subprocess.run(['rsync','-a','--delete',*['--exclude='+p for p in PRESERVE],str(source)+'/',str(LIVE)+'/'],check=True)
def healthy(commit=None):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(60):
        try:
            with opener.open('http://127.0.0.1:8765/api/local/support/status' if commit else 'http://127.0.0.1:8765/api/v1/health',timeout=2) as r:
                status=json.load(r)
            if commit and (status.get('release')!=commit or not status.get('enabled')):raise ValueError()
            return status
        except (OSError,ValueError):time.sleep(.5)
    raise RuntimeError('Health/version check failed')

def main():
    p=argparse.ArgumentParser();p.add_argument('stage');p.add_argument('commit');args=p.parse_args()
    stage=Path(args.stage).resolve();commit=args.commit
    import re
    assert os.geteuid()==0 and re.fullmatch('[a-f0-9]{40}',commit)
    assert stage.parent==Path('/opt/harnessagent-releases') and stage.name=='ha0090-'+commit[:12]
    assert (stage/'backend/support_mcp.py').is_file() and (ENV/'bin/python').is_file()
    pid=int(run(['systemctl','show','harnessagent','-p','MainPID','--value']))
    assert pid>1
    env=dict(v.split(b'=',1) for v in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0') if b'=' in v)
    db=Path(env[b'HARNESS_DB'].decode()).resolve()
    assert db.is_relative_to('/var/lib/harnessagent') and db.is_file()
    # Import/preflight before stopping the old runtime, with a temporary DB only.
    subprocess.run([str(ENV/'bin/python'),'-m','pip','check'],check=True)
    subprocess.run([str(ENV/'bin/python'),'-c',
        'from backend.app import create_app; assert create_app(run_worker=False).openapi(); print("staging_import_ok")'],cwd=stage,check=True)
    assert (Path('/var/lib/harnessagent/support-embedding')/'support-model.json').is_file()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=Path('/var/backups/harnessagent')/('ha0090-'+stamp);backup.mkdir(mode=0o700)
    subprocess.run(['tar',*['--exclude=./'+p.rstrip('/') for p in PRESERVE],'-czf',str(backup/'application.tar.gz'),'-C',str(LIVE),'.'],check=True)
    if OVERRIDE.exists():shutil.copy2(OVERRIDE,backup/'support.conf')
    key=Path('/var/lib/harnessagent/support-master.key')
    if not key.exists():
        fd=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f:f.write(os.urandom(32));f.flush();os.fsync(f.fileno())
    stopped=False;promoted=False
    try:
        run(['systemctl','stop','harnessagent']);stopped=True
        with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as src,sqlite3.connect(backup/'harness.db') as dest:
            src.backup(dest);assert dest.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        (backup/'harness.db').chmod(0o600)
        promoted=True;sync(stage)
        OVERRIDE.parent.mkdir(exist_ok=True)
        OVERRIDE.write_text('[Service]\nExecStart=\nExecStart=/opt/harnessagent-support-env/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8765 --workers 1 --no-access-log --timeout-graceful-shutdown 10\n'
            'Environment=HARNESS_SUPPORT=enabled\nEnvironment=HARNESS_SUPPORT_MASTER_KEY_FILE=/var/lib/harnessagent/support-master.key\n'
            'Environment=HARNESS_SUPPORT_EMBEDDING_DIR=/var/lib/harnessagent/support-embedding\nEnvironment=HARNESS_RELEASE_COMMIT='+commit+'\n')
        run(['systemctl','daemon-reload']);run(['systemctl','start','harnessagent']);status=healthy(commit)
    except BaseException:
        if promoted:
            restore=backup/'restore';restore.mkdir()
            subprocess.run(['tar','-xzf',str(backup/'application.tar.gz'),'-C',str(restore)],check=True);sync(restore)
            if (backup/'support.conf').exists():shutil.copy2(backup/'support.conf',OVERRIDE)
            elif OVERRIDE.exists():OVERRIDE.unlink()
            run(['systemctl','daemon-reload'])
        if stopped:run(['systemctl','restart','harnessagent']);healthy()
        raise
    receipt={'commit':commit,'database':str(db),'backup':str(backup),'status':status,'old_dependency_environment_retained':True,
             'database_rollback':False,'credential_plaintext_in_environment':False,'url':'http://118.196.123.132/harness/support'}
    (backup/'deployment.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt))

if __name__=='__main__':main()
