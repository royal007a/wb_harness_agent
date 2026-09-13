"""Interactively configure the local Baidu OAuth connector without exposing secrets."""
import getpass
import os
import subprocess
import sys

import keyring
from keyring.errors import KeyringError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.baidu_netdisk import CLIENT_SECRET_ACCOUNT, KEYCHAIN_SERVICE

APP_KEY_ENV = 'HARNESS_BAIDUPAN_CLIENT_ID'
LAUNCHD_LABEL = 'local.harnessagent.workbench'
CONFIRMATION = 'CONFIGURE'


class ConfigurationError(Exception):
    pass


def valid_app_key(value):
    return isinstance(value, str) and 8 <= len(value) <= 128 and not any(char.isspace() for char in value)


def valid_client_secret(value):
    return isinstance(value, str) and 1 <= len(value) <= 4096 and not any(char.isspace() for char in value)


def launchctl_commands(app_key, uid):
    target = f'gui/{uid}/{LAUNCHD_LABEL}'
    return [
        ['launchctl', 'setenv', APP_KEY_ENV, app_key],
        ['launchctl', 'kickstart', '-k', target],
    ]


def configure(app_key, client_secret, *, set_password, run, uid):
    if not valid_app_key(app_key):
        raise ConfigurationError('App Key 格式无效。')
    if not valid_client_secret(client_secret):
        raise ConfigurationError('Client Secret 格式无效。')
    try:
        set_password(KEYCHAIN_SERVICE, CLIENT_SECRET_ACCOUNT, client_secret)
    except KeyringError as exc:
        raise ConfigurationError('无法写入 macOS Keychain。') from exc
    try:
        for command in launchctl_commands(app_key, uid):
            run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ConfigurationError('Keychain 已安全写入；本机服务未能重启，请检查 launchd 后重试。') from exc


def main(input_fn=input, secret_fn=getpass.getpass, stdout=sys.stdout):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print('拒绝：配置助手只能在交互式本机终端运行。', file=stdout)
        return 2
    print('百度网盘 OAuth 本机配置：不会显示或上传 Client Secret。', file=stdout)
    app_key = input_fn('Baidu App Key（公开标识）: ').strip()
    client_secret = secret_fn('Client Secret（输入不回显）: ')
    confirmed = input_fn(f'将写入本机 Keychain 并重启本地服务。输入 {CONFIRMATION} 继续: ').strip()
    if confirmed != CONFIRMATION:
        print('已取消；未写入任何配置。', file=stdout)
        return 0
    try:
        configure(app_key, client_secret, set_password=keyring.set_password, run=subprocess.run, uid=os.getuid())
    except ConfigurationError as exc:
        print(f'配置未完成：{exc}', file=stdout)
        return 1
    print('配置完成：App Key 已注入当前登录会话，Client Secret 已写入 Keychain。', file=stdout)
    print('打开 http://127.0.0.1:8765/connectors/baidu-netdisk 并点击“生成官方授权链接”。', file=stdout)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
