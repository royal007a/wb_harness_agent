"""Bounded JSON transport into a non-root, offline Colima VM container."""
import json
import os
import re
import selectors
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .analysis import MAX_BYTES, Problem, digest
from .store import uid

ROOT = Path(__file__).resolve().parents[1]
IMAGE_TAG = 'harnessagent-sandbox:0.1'
PROFILE_VERSION = 'colima-stdlib-v1'


def docker_command():
    executable = shutil.which('docker') or '/opt/homebrew/bin/docker'
    if not Path(executable).is_file():
        raise Problem('SANDBOX_UNAVAILABLE', 'Docker CLI 不可用。')
    return [executable, '--context', 'colima']


def docker(args, timeout=15):
    try:
        return subprocess.run(docker_command() + args, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Problem('SANDBOX_UNAVAILABLE', '无法在期限内联系 Colima Docker。') from None


def image_id():
    response = docker(['image', 'inspect', IMAGE_TAG, '--format', '{{.Id}}'])
    ident = response.stdout.decode().strip()
    if response.returncode or not re.fullmatch(r'sha256:[a-f0-9]{64}', ident):
        raise Problem('SANDBOX_IMAGE_MISSING', '请先构建 Harness 沙箱镜像。')
    return ident


def profile_args(input_dir, name, image):
    return ['create', '--interactive', '--name', name, '--label', 'local.harnessagent.sandbox=true',
            '--network', 'none', '--read-only', '--user', '65532:65532', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges=true', '--cpus', '0.5', '--memory', '256m',
            '--memory-swap', '256m', '--pids-limit', '32', '--ulimit', 'nofile=128:128',
            '--ulimit', 'fsize=8388608:8388608', '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777',
            '--tmpfs', '/outputs:rw,noexec,nosuid,nodev,size=32m,mode=1777',
            '--mount', f'type=bind,src={input_dir},dst=/inputs,readonly',
            '--env', 'PYTHONDONTWRITEBYTECODE=1', '--env', 'PYTHONUNBUFFERED=1', image]


def profile_digest():
    recipe = (ROOT / 'sandbox/Dockerfile').read_bytes() + (ROOT / 'sandbox/runner.py').read_bytes()
    return digest(recipe + json.dumps(profile_args('/inputs-placeholder', 'name-placeholder', 'image-placeholder')).encode())


class DockerSandbox:
    def __init__(self, raw, check=lambda: None, emit=lambda *_: None, step_timeout=15, image=None):
        if not raw or len(raw) > MAX_BYTES:
            raise Problem('INVALID_RESOURCE', '沙箱输入大小超限。')
        if not 0 < step_timeout <= 60:
            raise Problem('VALIDATION_ERROR', '沙箱步骤超时需在 0–60 秒内。')
        self.check, self.emit, self.step_timeout = check, emit, step_timeout
        self.container_id = None
        self.process = None
        self.buffer = bytearray()
        self.image = image or image_id()
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', self.image):
            raise Problem('SANDBOX_IMAGE_MISSING', '沙箱只能使用不可变镜像 ID。')
        parent = ROOT / '.local/sandbox-inputs'
        parent.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix='run-', dir=parent)
        self.input_dir = Path(self.directory.name)
        self.input_dir.chmod(0o755)
        data = self.input_dir / 'data.csv'
        data.write_bytes(raw)
        data.chmod(0o444)
        name = uid('harnessagent')
        try:
            self.check()
            created = docker(profile_args(str(self.input_dir), name, self.image))
            ident = created.stdout.decode().strip()
            if created.returncode or not re.fullmatch(r'[a-f0-9]{64}', ident):
                raise Problem('SANDBOX_START_FAILED', '隔离容器创建失败。')
            self.container_id = ident
            self.process = subprocess.Popen(docker_command() + ['start', '--attach', '--interactive', ident],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.emit('sandbox.started', {'container_id': ident, 'image_id': self.image, 'profile': PROFILE_VERSION})
        except BaseException:
            self.cleanup()
            raise

    def request(self, payload):
        self.check()
        if not self.process or self.process.poll() is not None:
            raise Problem('SANDBOX_EXITED', '隔离执行进程已退出。')
        encoded = json.dumps(payload, ensure_ascii=True, allow_nan=False).encode() + b'\n'
        if len(encoded) > 32768:
            raise Problem('SANDBOX_INPUT_LIMIT', '代码或变量超过 32 KiB。')
        deadline = time.monotonic() + self.step_timeout
        # Nonblocking writes and reads keep cancellation effective even when
        # untrusted code interferes with stdin or writes directly to stdout.
        incoming, outgoing = self.process.stdout.fileno(), self.process.stdin.fileno()
        os.set_blocking(incoming, False)
        os.set_blocking(outgoing, False)
        try:
            offset = 0
            with selectors.DefaultSelector() as selector:
                selector.register(incoming, selectors.EVENT_READ)
                selector.register(outgoing, selectors.EVENT_WRITE)
                while True:
                    self.check()
                    if time.monotonic() > deadline:
                        raise Problem('SANDBOX_TIMEOUT', '代码步骤超过墙钟时间上限。')
                    for key, mask in selector.select(.05):
                        if key.fd == outgoing:
                            offset += os.write(outgoing, encoded[offset:])
                            if offset == len(encoded):
                                selector.unregister(outgoing)
                        else:
                            chunk = os.read(incoming, 16384)
                            if not chunk:
                                raise Problem('SANDBOX_EXITED', '代码进程退出或超过资源上限。')
                            self.buffer.extend(chunk)
                            if len(self.buffer) > 131072:
                                raise Problem('SANDBOX_OUTPUT_LIMIT', '代码输出超过 128 KiB。')
                            if b'\n' in self.buffer:
                                line, _, rest = self.buffer.partition(b'\n')
                                if rest:
                                    raise Problem('SANDBOX_PROTOCOL_ERROR', '沙箱返回了多余协议消息。')
                                self.buffer.clear()
                                result = json.loads(line)
                                self.validate_response(result)
                                return result
        except (ValueError, OSError):
            self.cleanup()
            raise Problem('SANDBOX_PROTOCOL_ERROR', '隔离进程返回了无效 JSON 协议。') from None
        except BaseException:
            self.cleanup()
            raise

    @staticmethod
    def validate_response(result):
        if not isinstance(result, dict) or set(result) != {'output', 'logs', 'is_final_answer', 'error'}:
            raise ValueError('Unexpected response')
        if not isinstance(result['logs'], str) or type(result['is_final_answer']) is not bool:
            raise ValueError('Invalid response fields')
        if result['error'] is not None and not isinstance(result['error'], str):
            raise ValueError('Invalid error')
        json.dumps(result, allow_nan=False)

    def execute(self, code):
        if not isinstance(code, str):
            raise Problem('VALIDATION_ERROR', '代码必须为文本。')
        self.emit('code.execution.requested', {'code_sha256': digest(code.encode()), 'bytes': len(code.encode())})
        result = self.request({'code': code})
        self.emit('code.execution.completed', {'is_final_answer': result['is_final_answer'], 'has_error': result['error'] is not None,
                                               'logs_sha256': digest(result['logs'].encode())})
        return result

    def inspect(self):
        if not self.container_id:
            raise Problem('SANDBOX_EXITED', '容器已清理。')
        result = docker(['inspect', self.container_id])
        if result.returncode:
            raise Problem('SANDBOX_UNAVAILABLE', '无法读取容器配置。')
        return json.loads(result.stdout)[0]

    def cleanup(self):
        if self.container_id:
            ident = self.container_id
            result = docker(['rm', '--force', ident], timeout=10)
            if result.returncode:
                existing = docker(['container', 'ls', '-aq', '--no-trunc', '--filter', 'id=' + ident])
                if existing.returncode or existing.stdout.strip():
                    raise Problem('CLEANUP_FAILED', '隔离容器清理失败，需检查该容器 ID。')
            self.container_id = None
            self.emit('sandbox.cleaned', {'container_id': ident})
        if self.process:
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
            self.process.stdin.close()
            self.process.stdout.close()
            self.process = None
        self.directory.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cleanup()
