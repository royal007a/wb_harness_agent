"""Safely hand a user-provided Baidu share URL to the installed macOS client."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
from urllib.parse import urlsplit


OFFICIAL_CLIENT = Path('/Applications/BaiduNetdisk_mac.app')
SHARE_HOST = 'pan.baidu.com'
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024 * 1024


class InputError(ValueError):
    """An intentionally non-sensitive input validation error."""


def validate_share_url(raw):
    """Return a non-secret URL digest after enforcing the official share shape."""
    if not isinstance(raw, str) or not 12 <= len(raw) <= 4096 or any(ch.isspace() for ch in raw):
        raise InputError('invalid share URL')
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise InputError('invalid share URL') from exc
    if (parsed.scheme != 'https' or parsed.hostname != SHARE_HOST or port is not None
            or parsed.username is not None or parsed.password is not None
            or not parsed.path.startswith('/s/') or len(parsed.path) > 1024 or parsed.fragment):
        raise InputError('invalid share URL')
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def handoff(share_url, *, dry_run=False, runner=subprocess.run):
    """Open only the official local client; this program makes no network request."""
    url_sha256 = validate_share_url(share_url)
    if not OFFICIAL_CLIENT.is_dir():
        raise InputError('official client is not installed')
    if not dry_run:
        runner(['open', '-a', str(OFFICIAL_CLIENT), share_url], check=True,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {'status': 'validated' if dry_run else 'handoff_started',
            'client': OFFICIAL_CLIENT.name, 'share_url_sha256': url_sha256,
            'network_requests_by_script': 0}


def claim_download(candidate, *, home=None):
    """Accept an explicit, ordinary file in Downloads without reading its contents."""
    home = Path(home) if home is not None else Path.home()
    downloads = (home / 'Downloads').resolve(strict=True)
    requested = Path(candidate).expanduser()
    if requested.is_symlink():
        raise InputError('download must not be a symlink')
    resolved = requested.resolve(strict=True)
    if downloads not in (resolved, *resolved.parents):
        raise InputError('download must be under the user Downloads directory')
    mode = resolved.stat().st_mode
    size = resolved.stat().st_size
    if not stat.S_ISREG(mode) or not 0 < size <= MAX_DOWNLOAD_BYTES:
        raise InputError('download must be a bounded regular file')
    return {'status': 'download_claimed', 'path': str(resolved), 'size_bytes': size,
            'content_read_by_script': False}


def read_url_from_stdin():
    value = sys.stdin.readline(4097)
    if len(value) > 4096 or sys.stdin.read(1):
        raise InputError('provide exactly one share URL line')
    return value.rstrip('\r\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    handoff_parser = actions.add_parser('handoff')
    handoff_parser.add_argument('--stdin', action='store_true', required=True,
                                help='read exactly one HTTPS share URL line from standard input')
    handoff_parser.add_argument('--dry-run', action='store_true')
    claim_parser = actions.add_parser('claim')
    claim_parser.add_argument('--file', required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == 'handoff':
            result = handoff(read_url_from_stdin(), dry_run=args.dry_run)
        else:
            result = claim_download(args.file)
    except (InputError, OSError, subprocess.SubprocessError):
        print(json.dumps({'status': 'error', 'code': 'INVALID_OR_UNAVAILABLE_INPUT'}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
