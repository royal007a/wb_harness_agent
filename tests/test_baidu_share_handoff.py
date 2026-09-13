import importlib.util
import json
from pathlib import Path
import sys
from io import StringIO

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/baidu-netdisk-download/scripts/baidu_share_handoff.py'
SPEC = importlib.util.spec_from_file_location('baidu_share_handoff', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_valid_share_handoff_only_exposes_digest(monkeypatch, tmp_path):
    link = 'https://pan.baidu.com/s/example-share?pwd=secret-code'
    fake_app = tmp_path / 'BaiduNetdisk_mac.app'
    fake_app.mkdir()
    calls = []
    monkeypatch.setattr(MODULE, 'OFFICIAL_CLIENT', fake_app)
    result = MODULE.handoff(link, runner=lambda command, **kwargs: calls.append((command, kwargs)))
    encoded = json.dumps(result)
    assert result['status'] == 'handoff_started'
    assert link not in encoded and 'secret-code' not in encoded
    assert calls[0][0] == ['open', '-a', str(fake_app), link]
    assert result['network_requests_by_script'] == 0


@pytest.mark.parametrize('link', [
    'http://pan.baidu.com/s/x', 'https://evil.example/s/x', 'https://pan.baidu.com/file/x',
    'https://pan.baidu.com/s/x#fragment', 'https://user@pan.baidu.com/s/x',
])
def test_rejects_noncanonical_or_unsafe_share_urls(link):
    with pytest.raises(MODULE.InputError):
        MODULE.validate_share_url(link)


def test_claim_requires_explicit_regular_file_inside_downloads(tmp_path):
    downloads = tmp_path / 'Downloads'
    downloads.mkdir()
    valid = downloads / 'report.pdf'
    valid.write_bytes(b'approved local file')
    assert MODULE.claim_download(valid, home=tmp_path) == {
        'status': 'download_claimed', 'path': str(valid), 'size_bytes': len(valid.read_bytes()),
        'content_read_by_script': False,
    }
    outside = tmp_path / 'other.pdf'
    outside.write_bytes(b'outside')
    with pytest.raises(MODULE.InputError):
        MODULE.claim_download(outside, home=tmp_path)
    linked = downloads / 'linked.pdf'
    linked.symlink_to(valid)
    with pytest.raises(MODULE.InputError):
        MODULE.claim_download(linked, home=tmp_path)


def test_cli_requires_stdin_and_never_echoes_share_value(monkeypatch, tmp_path, capsys):
    fake_app = tmp_path / 'no-client.app'
    monkeypatch.setattr(MODULE, 'OFFICIAL_CLIENT', fake_app)
    monkeypatch.setattr(sys, 'stdin', StringIO('https://pan.baidu.com/s/example?pwd=secret-code\n'))
    assert MODULE.main(['handoff', '--stdin', '--dry-run']) == 1
    captured = capsys.readouterr()
    assert 'secret-code' not in captured.out + captured.err
