import io
import subprocess

import pytest

from harness.configure_baidu_netdisk import (APP_KEY_ENV, CLIENT_SECRET_ACCOUNT, CONFIRMATION,
                                              ConfigurationError, KEYCHAIN_SERVICE, LAUNCHD_LABEL,
                                              configure, launchctl_commands, main)


def test_configuration_writes_only_keychain_and_public_launchd_environment():
    writes, commands = [], []
    configure('app-key-123456', 'client-secret-value',
              set_password=lambda service, account, value: writes.append((service, account, value)),
              run=lambda command, **kwargs: commands.append((command, kwargs)), uid=501)
    assert writes == [(KEYCHAIN_SERVICE, CLIENT_SECRET_ACCOUNT, 'client-secret-value')]
    assert [command for command, _ in commands] == [
        ['launchctl', 'setenv', APP_KEY_ENV, 'app-key-123456'],
        ['launchctl', 'kickstart', '-k', f'gui/501/{LAUNCHD_LABEL}'],
    ]
    assert all(kwargs['stdout'] is not None and kwargs['stderr'] is not None for _, kwargs in commands)


@pytest.mark.parametrize(('app_key', 'client_secret'), [
    ('short', 'secret'), ('valid-app-key', ''), ('contains space', 'secret'), ('valid-app-key', 'has space'),
])
def test_configuration_rejects_invalid_values_without_side_effects(app_key, client_secret):
    writes, commands = [], []
    with pytest.raises(ConfigurationError):
        configure(app_key, client_secret, set_password=lambda *value: writes.append(value),
                  run=lambda *value, **kwargs: commands.append(value), uid=501)
    assert writes == [] and commands == []


def test_configuration_command_shape_exposes_no_client_secret():
    commands = launchctl_commands('app-key-123456', 501)
    joined = ' '.join(' '.join(command) for command in commands)
    assert 'client-secret' not in joined
    assert CLIENT_SECRET_ACCOUNT not in joined


def test_configuration_launchd_failure_never_echoes_client_secret():
    writes = []
    with pytest.raises(ConfigurationError) as error:
        configure('app-key-123456', 'client-secret-value',
                  set_password=lambda *value: writes.append(value),
                  run=lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.CalledProcessError(1, args[0])), uid=501)
    assert writes == [(KEYCHAIN_SERVICE, CLIENT_SECRET_ACCOUNT, 'client-secret-value')]
    assert 'client-secret-value' not in str(error.value)


def test_main_rejects_noninteractive_terminal(monkeypatch):
    monkeypatch.setattr('sys.stdin', io.StringIO())
    monkeypatch.setattr('sys.stdout', io.StringIO())
    output = io.StringIO()
    assert main(stdout=output) == 2
    assert '拒绝' in output.getvalue()


def test_main_cancel_does_not_write(monkeypatch):
    class TTY(io.StringIO):
        def isatty(self):
            return True
    monkeypatch.setattr('sys.stdin', TTY())
    monkeypatch.setattr('sys.stdout', TTY())
    output = TTY()
    answers = iter(['app-key-123456', CONFIRMATION.lower()])
    assert main(input_fn=lambda _: next(answers), secret_fn=lambda _: 'client-secret-value', stdout=output) == 0
    assert '已取消' in output.getvalue()
