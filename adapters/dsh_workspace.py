"""Owned workspace journal. Recovery never guesses paths or kills recovered PIDs."""
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time


def owned_root(value):
    root = Path(value).absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('DSH workspace root must not contain symlinks')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = root.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError('DSH workspace root must be private and owned')
    registry = root / '.registry'
    registry.mkdir(mode=0o700, exist_ok=True)
    if registry.is_symlink() or registry.stat().st_uid != os.getuid():
        raise ValueError('DSH workspace registry is invalid')
    return root


def _journal(root, name, value):
    path = root / '.registry' / (name + '.json')
    temporary = path.with_suffix('.new')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(value, out)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)


class OwnedWorkspace:
    def __init__(self, runtime_root):
        self.root = owned_root(runtime_root)
        self.path = Path(tempfile.mkdtemp(prefix='run-', dir=self.root))
        self.path.chmod(0o700)
        info = self.path.stat()
        self.record = {'version': 1, 'name': self.path.name, 'device': info.st_dev,
                       'inode': info.st_ino, 'pgid': None}
        self.lease = os.open(self.path / '.lease', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # This durable journal exists before a subprocess or any document text.
        _journal(self.root, self.path.name, self.record)

    def started(self, pgid):
        self.record['pgid'] = pgid
        # Record the process group before writing the prompt to its stdin.
        _journal(self.root, self.path.name, self.record)

    def close(self):
        os.close(self.lease)
        return cleanup_workspaces(self.root, only=self.path.name, wait_seconds=3)


def _cleanup_one(root, entry):
    if entry.is_symlink() or not re.fullmatch(r'run-[a-z0-9_]+\.json', entry.name):
        return 'retained'
    try:
        fd = os.open(entry, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as src:
            raw = src.read(4097)
        record = json.loads(raw)
        name = entry.stem
        if (len(raw) > 4096 or not isinstance(record, dict) or
            set(record) != {'version', 'name', 'device', 'inode', 'pgid'} or
            record['version'] != 1 or record['name'] != name or
            type(record['device']) is not int or type(record['inode']) is not int or
            (record['pgid'] is not None and (type(record['pgid']) is not int or record['pgid'] <= 1))):
            return 'retained'
        workspace = root / name
        info = workspace.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or
            (info.st_dev, info.st_ino) != (record['device'], record['inode'])):
            return 'retained'
        lease = os.open(workspace / '.lease', os.O_RDWR | os.O_NOFOLLOW)
        try:
            try:
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return 'pending'
            if record['pgid'] is not None:
                try:
                    os.killpg(record['pgid'], 0)
                    return 'pending'
                except ProcessLookupError:
                    pass
                except PermissionError:
                    return 'pending'
            # Do not follow even an internal symlink. Preserve for inspection.
            for directory, dirs, files in os.walk(workspace, followlinks=False):
                if any((Path(directory) / part).is_symlink() for part in (*dirs, *files)):
                    return 'retained'
            shutil.rmtree(workspace)
            entry.unlink()
            return 'cleaned'
        finally:
            os.close(lease)
    except (OSError, ValueError, TypeError):
        return 'retained'


def cleanup_workspaces(runtime_root, *, only=None, wait_seconds=5):
    root = owned_root(runtime_root)
    deadline = time.monotonic() + wait_seconds
    entries = [p for p in (root / '.registry').iterdir()
               if p.suffix == '.json' and (only is None or p.stem == only)]
    result = {'cleaned': 0, 'pending': 0, 'retained': 0}
    while entries:
        waiting = []
        for entry in entries:
            status = _cleanup_one(root, entry)
            if status == 'pending' and time.monotonic() < deadline:
                waiting.append(entry)
            else:
                result[status] += 1
        entries = waiting
        if entries:
            time.sleep(.05)
    return result
