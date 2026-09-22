"""One-shot, no-network container boundary for an immutable external Skill package."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .analysis import Problem, digest
from .sandbox import docker, docker_command
from .store import uid


ROOT = Path(__file__).resolve().parents[1]
IMAGE_TAG = 'harnessagent-external-skill:0.1'
PROFILE_VERSION = 'external-skill-stdlib-v1'
MAX_PROTOCOL_BYTES = 32 * 1024


def image_id():
    response = docker(['image', 'inspect', IMAGE_TAG, '--format', '{{.Id}}'])
    ident = response.stdout.decode().strip()
    if response.returncode or not re.fullmatch(r'sha256:[a-f0-9]{64}', ident):
        raise Problem('EXTERNAL_SKILL_IMAGE_MISSING', '请先构建外部 Skill 隔离镜像。', 503)
    return ident


def profile_args(skill_dir, input_dir, name, image):
    return [
        'create', '--name', name, '--label', 'local.harnessagent.external-skill=true',
        '--network', 'none', '--read-only', '--user', '65532:65532', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges=true', '--cpus', '0.25', '--memory', '128m',
        '--memory-swap', '128m', '--pids-limit', '24', '--ulimit', 'nofile=64:64',
        '--ulimit', 'fsize=1048576:1048576',
        '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=8m,mode=1777',
        '--tmpfs', '/work:rw,noexec,nosuid,nodev,size=8m,mode=1777',
        '--mount', f'type=bind,src={skill_dir},dst=/skill,readonly',
        '--mount', f'type=bind,src={input_dir},dst=/inputs,readonly',
        '--workdir', '/work', '--env', 'PYTHONDONTWRITEBYTECODE=1',
        '--env', 'PYTHONUNBUFFERED=1', image,
    ]


def profile_digest():
    recipe = (ROOT / 'sandbox/external-skill.Dockerfile').read_bytes() + (ROOT / 'sandbox/external_runner.py').read_bytes()
    args = profile_args('/skill-placeholder', '/input-placeholder', 'name-placeholder', 'image-placeholder')
    return digest(recipe + json.dumps(args, separators=(',', ':')).encode())


class ExternalSkillSandbox:
    """Runs only a fixed Python entrypoint; package code never runs on the host."""

    def __init__(self, skill_dir, payload, *, timeout_seconds=10, image=None):
        if not isinstance(payload, dict):
            raise Problem('VALIDATION_ERROR', '外部 Skill 输入必须是 JSON object。', 422)
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
        if len(encoded) > MAX_PROTOCOL_BYTES:
            raise Problem('EXTERNAL_SKILL_INPUT_LIMIT', '外部 Skill 输入超过 32 KiB。', 413)
        if not 0 < timeout_seconds <= 30:
            raise Problem('VALIDATION_ERROR', '外部 Skill 超时需在 1–30 秒。', 422)
        self.skill_dir = Path(skill_dir)
        self.payload = encoded
        self.timeout_seconds = timeout_seconds
        self.image = image or image_id()
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', self.image):
            raise Problem('EXTERNAL_SKILL_IMAGE_MISSING', '外部 Skill 只能使用不可变镜像 ID。', 503)
        self.container_id = None
        self._input_directory = None

    def _cleanup(self):
        cleanup_error = None
        if self.container_id:
            ident = self.container_id
            response = docker(['rm', '--force', ident], timeout=10)
            if response.returncode:
                existing = docker(['container', 'ls', '-aq', '--no-trunc', '--filter', 'id=' + ident])
                if existing.returncode or existing.stdout.strip():
                    cleanup_error = Problem('EXTERNAL_SKILL_CLEANUP_FAILED', '隔离容器清理失败，需要人工检查。', 503)
            self.container_id = None
        if self._input_directory:
            self._input_directory.cleanup()
            self._input_directory = None
        if cleanup_error:
            raise cleanup_error

    def execute(self):
        if not self.skill_dir.is_dir():
            raise Problem('EXTERNAL_SKILL_PACKAGE_TAMPERED', '外部 Skill 受控包目录缺失。', 409)
        parent = ROOT / '.local/external-skill-inputs'
        parent.mkdir(parents=True, exist_ok=True)
        self._input_directory = tempfile.TemporaryDirectory(prefix='exec-', dir=parent)
        input_dir = Path(self._input_directory.name)
        input_dir.chmod(0o755)
        request = input_dir / 'request.json'
        request.write_bytes(self.payload)
        request.chmod(0o444)
        started = time.monotonic()
        try:
            name = uid('external-skill')
            created = docker(profile_args(str(self.skill_dir), str(input_dir), name, self.image), timeout=15)
            ident = created.stdout.decode().strip()
            if created.returncode or not re.fullmatch(r'[a-f0-9]{64}', ident):
                raise Problem('EXTERNAL_SKILL_START_FAILED', '隔离外部 Skill 容器创建失败。', 503)
            self.container_id = ident
            try:
                completed = subprocess.run(
                    docker_command() + ['start', '--attach', ident], capture_output=True,
                    timeout=self.timeout_seconds, check=False,
                )
            except subprocess.TimeoutExpired:
                raise Problem('EXTERNAL_SKILL_TIMEOUT', '外部 Skill 超过墙钟时间上限。', 408) from None
            if len(completed.stdout) > MAX_PROTOCOL_BYTES:
                raise Problem('EXTERNAL_SKILL_OUTPUT_LIMIT', '外部 Skill 输出超过 32 KiB。', 413)
            if completed.returncode:
                raise Problem('EXTERNAL_SKILL_EXECUTION_FAILED', '外部 Skill 执行失败。', 422)
            try:
                result = json.loads(completed.stdout)
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise Problem('EXTERNAL_SKILL_PROTOCOL_ERROR', '外部 Skill 未返回单个 JSON 结果。', 422) from None
            if not isinstance(result, dict) or set(result) != {'output'} or not isinstance(result['output'], dict):
                raise Problem('EXTERNAL_SKILL_PROTOCOL_ERROR', '外部 Skill 返回不符合受限协议。', 422)
            json.dumps(result['output'], ensure_ascii=False, allow_nan=False)
            return result['output'], {
                'isolation_profile': PROFILE_VERSION,
                'profile_sha256': profile_digest(),
                'image_id': self.image,
                'duration_ms': round((time.monotonic() - started) * 1000),
                'container_cleaned': True,
            }
        finally:
            self._cleanup()
