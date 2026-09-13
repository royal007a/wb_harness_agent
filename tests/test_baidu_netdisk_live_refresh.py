from types import SimpleNamespace

import pytest

from harness.baidu_netdisk_live_refresh import APP_KEY_ENV, LAUNCHD_LABEL, load_launchd_app_key


def test_loads_only_public_app_key_from_launchd():
    environment, calls = {}, []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout='app-key-123456\n')
    load_launchd_app_key(environ=environment, run=run, uid=501)
    assert environment == {APP_KEY_ENV: 'app-key-123456'}
    assert calls[0][0] == ['launchctl', 'getenv', APP_KEY_ENV]
    assert calls[0][1]['stderr'] is not None


def test_does_not_call_launchd_when_process_already_has_public_app_key():
    environment = {APP_KEY_ENV: 'app-key-123456'}
    load_launchd_app_key(environ=environment, run=lambda *args, **kwargs: pytest.fail('should not run'), uid=501)


def test_loads_public_app_key_from_running_service_only_when_getenv_is_empty():
    environment, calls = {}, []
    def run(command, **kwargs):
        calls.append(command)
        if command[1] == 'getenv':
            return SimpleNamespace(returncode=0, stdout='')
        return SimpleNamespace(returncode=0, stdout='  HARNESS_BAIDUPAN_CLIENT_ID => app-key-123456\n')
    load_launchd_app_key(environ=environment, run=run, uid=501)
    assert environment == {APP_KEY_ENV: 'app-key-123456'}
    assert calls == [['launchctl', 'getenv', APP_KEY_ENV], ['launchctl', 'print', f'gui/501/{LAUNCHD_LABEL}']]


@pytest.mark.parametrize('value', ['', 'short', 'with space'])
def test_rejects_missing_or_invalid_launchd_value(value):
    with pytest.raises(RuntimeError):
        load_launchd_app_key(environ={}, run=lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=value), uid=501)
