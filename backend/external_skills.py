"""Strictly packaged, default-disabled external Skill registry and runner."""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from jsonschema import Draft202012Validator

from .analysis import Problem, digest
from .external_skill_sandbox import ExternalSkillSandbox, PROFILE_VERSION, image_id
from .store import dumps, now, uid


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'specs/v1/external-skill-runtime.schema.json').read_text())
PACKAGE_ROOT = ROOT / '.local/external-skill-packages'
MAX_PACKAGE_BYTES = 128 * 1024
SENSITIVE_INPUT = re.compile(r'(?:\b(?:api[_ -]?key|client[_ -]?secret|access[_ -]?token|refresh[_ -]?token|password)\s*[:=]|\bsk-[A-Za-z0-9_-]{10,}|\bAKIA[0-9A-Z]{16}\b)', re.I)


def validate_contract(name, value):
    schema = {'$ref': '#/$defs/' + name, '$defs': CONTRACT['$defs']}
    if list(Draft202012Validator(schema).iter_errors(value)):
        raise Problem('VALIDATION_ERROR', '请求不符合 External Skill Runtime 契约。', 422)


class ExternalSkillRuntime:
    """Local-admin boundary; it intentionally has no model, MCP, or network route."""

    def __init__(self, store, *, enabled=None, sandbox_cls=ExternalSkillSandbox):
        self.store = store
        self._enabled = enabled
        self.sandbox_cls = sandbox_cls

    def enabled(self):
        return self._enabled if self._enabled is not None else os.getenv('HARNESS_EXTERNAL_SKILLS') == 'enabled'

    @staticmethod
    def _idempotency_key(key):
        if not isinstance(key, str) or not 1 <= len(key) <= 128:
            raise Problem('VALIDATION_ERROR', '必须提供 1–128 字符的 Idempotency-Key。', 422)

    def _replay(self, scope, key, request_digest):
        self._idempotency_key(key)
        with self.store.lock:
            row = self.store.db.execute('SELECT digest,response FROM idempotency WHERE scope=? AND key=?', (scope, key)).fetchone()
        if not row:
            return None
        if row['digest'] != request_digest:
            raise Problem('CONFLICT', '同一幂等键已用于不同请求。', 409)
        return json.loads(row['response'])

    @staticmethod
    def _manifest_and_entry(raw):
        if not raw or len(raw) > MAX_PACKAGE_BYTES:
            raise Problem('EXTERNAL_SKILL_PACKAGE_TOO_LARGE', '外部 Skill ZIP 必须为 1–128 KiB。', 413)
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
            infos = archive.infolist()
            allowed = {'manifest.json', 'entry.py'}
            if {item.filename for item in infos} != allowed or len(infos) != 2:
                raise Problem('EXTERNAL_SKILL_PACKAGE_INVALID', 'ZIP 根目录只能包含 manifest.json 与 entry.py。', 422)
            for item in infos:
                mode = (item.external_attr >> 16) & 0o170000
                if item.is_dir() or item.filename.startswith('/') or '..' in Path(item.filename).parts or mode == 0o120000:
                    raise Problem('EXTERNAL_SKILL_PACKAGE_INVALID', 'ZIP 不允许目录、链接或路径穿越。', 422)
                if item.file_size > 64 * 1024 or item.compress_size > MAX_PACKAGE_BYTES:
                    raise Problem('EXTERNAL_SKILL_PACKAGE_INVALID', 'ZIP 文件大小超限。', 422)
            manifest_raw = archive.read('manifest.json')
            entry_raw = archive.read('entry.py')
        except Problem:
            raise
        except (OSError, zipfile.BadZipFile, KeyError):
            raise Problem('EXTERNAL_SKILL_PACKAGE_INVALID', '外部 Skill 必须是有效 ZIP。', 422) from None
        try:
            manifest = json.loads(manifest_raw.decode('utf-8'))
            entry_raw.decode('utf-8')
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise Problem('EXTERNAL_SKILL_PACKAGE_INVALID', 'manifest 和 entry.py 必须是 UTF-8。', 422) from None
        validate_contract('skill_manifest', manifest)
        if SENSITIVE_INPUT.search(manifest_raw.decode('utf-8')) or SENSITIVE_INPUT.search(entry_raw.decode('utf-8')):
            raise Problem('SENSITIVE_INPUT_REJECTED', '外部 Skill 包不得包含凭证样式内容。', 422)
        return manifest, manifest_raw, entry_raw, digest(manifest_raw + b'\0' + entry_raw)

    def runtime_status(self):
        image_state, image = 'not_checked', None
        try:
            image = image_id()
            image_state = 'available'
        except Problem as exc:
            image_state = exc.code.lower()
        blockers = []
        if not self.enabled():
            blockers.append('external_skill_runtime_disabled')
        if image_state != 'available':
            blockers.append(image_state)
        return {
            'mode': 'external-skill-runtime@1',
            'runtime_enabled': self.enabled(),
            'isolation_profile': PROFILE_VERSION,
            'image_id': image,
            'package_sources': ['local_zip_upload_only'],
            'network': 'denied',
            'host_paths': 'denied_except_immutable_package_and_request_mounts',
            'credentials': 'not_injected',
            'blockers': blockers,
        }

    def packages(self):
        return {'items': self.store.external_skill_packages(), 'runtime': self.runtime_status()}

    def register_package(self, raw, metadata, key):
        validate_contract('package_registration', metadata)
        request_digest = digest(raw + dumps(metadata).encode())
        replay = self._replay('external-skills:register', key, request_digest)
        if replay:
            return replay
        manifest, manifest_raw, entry_raw, content_sha256 = self._manifest_and_entry(raw)
        PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
        with self.store.transaction() as db:
            existing = db.execute('SELECT doc FROM external_skill_packages WHERE content_sha256=?', (content_sha256,)).fetchone()
            if existing:
                package = json.loads(existing['doc'])
            else:
                target = PACKAGE_ROOT / content_sha256
                if target.exists():
                    try:
                        existing_manifest = (target / 'manifest.json').read_bytes()
                        existing_entry = (target / 'entry.py').read_bytes()
                    except OSError:
                        raise Problem('EXTERNAL_SKILL_PACKAGE_TAMPERED', '受控包目录不可读，拒绝覆盖。', 409) from None
                    if digest(existing_manifest + b'\0' + existing_entry) != content_sha256:
                        raise Problem('EXTERNAL_SKILL_PACKAGE_TAMPERED', '受控包目录摘要冲突，拒绝覆盖。', 409)
                else:
                    temporary = Path(tempfile.mkdtemp(prefix='.stage-', dir=PACKAGE_ROOT))
                    try:
                        (temporary / 'manifest.json').write_bytes(manifest_raw)
                        (temporary / 'entry.py').write_bytes(entry_raw)
                        for file in temporary.iterdir():
                            file.chmod(0o444)
                        temporary.chmod(0o555)
                        temporary.rename(target)
                    except BaseException:
                        shutil.rmtree(temporary, ignore_errors=True)
                        raise
                package = {
                    'id': uid('extpkg'), 'manifest': manifest, 'source_label': metadata['source_label'],
                    'content_sha256': content_sha256, 'storage': 'controlled_immutable_directory',
                    'created_at': now(), 'execution_count': 0,
                }
                db.execute('INSERT INTO external_skill_packages VALUES(?,?,?)', (package['id'], content_sha256, dumps(package)))
            db.execute('INSERT INTO idempotency VALUES(?,?,?,?)',
                       ('external-skills:register', key, request_digest, dumps(package)))
            return package

    @staticmethod
    def _verify_package(package):
        directory = PACKAGE_ROOT / package['content_sha256']
        try:
            manifest_raw = (directory / 'manifest.json').read_bytes()
            entry_raw = (directory / 'entry.py').read_bytes()
        except OSError:
            raise Problem('EXTERNAL_SKILL_PACKAGE_TAMPERED', '登记的外部 Skill 内容缺失。', 409) from None
        if digest(manifest_raw + b'\0' + entry_raw) != package['content_sha256']:
            raise Problem('EXTERNAL_SKILL_PACKAGE_TAMPERED', '登记的外部 Skill 内容摘要不匹配。', 409)
        manifest, _, _, _ = ExternalSkillRuntime._manifest_and_entry(_zip_bytes(manifest_raw, entry_raw))
        if manifest != package['manifest']:
            raise Problem('EXTERNAL_SKILL_PACKAGE_TAMPERED', '登记的外部 Skill manifest 已变化。', 409)
        return directory

    def execute(self, package_id, body, key):
        validate_contract('execution_request', body)
        self._idempotency_key(key)
        request_digest = digest(dumps({'package_id': package_id, 'body': body}).encode())
        replay = self._replay('external-skills:execute', key, request_digest)
        if replay:
            return replay
        if not self.enabled():
            raise Problem('EXTERNAL_SKILL_RUNTIME_DISABLED', '外部 Skill 运行时默认关闭；未读取包或启动容器。', 409)
        package = self.store.external_skill_package(package_id)
        directory = self._verify_package(package)
        output, sandbox_audit = self.sandbox_cls(directory, body['input']).execute()
        execution = {
            'execution_id': uid('extx'), 'package_id': package['id'], 'package_sha256': package['content_sha256'],
            'status': 'succeeded', 'output': output, 'isolation_profile': PROFILE_VERSION,
            'audit': {**sandbox_audit, 'input_sha256': digest(dumps(body['input']).encode()),
                      'output_sha256': digest(dumps(output).encode()), 'executed_at': now()},
        }
        with self.store.transaction() as db:
            old = db.execute('SELECT digest,response FROM idempotency WHERE scope=? AND key=?',
                             ('external-skills:execute', key)).fetchone()
            if old:
                if old['digest'] != request_digest:
                    raise Problem('CONFLICT', '同一幂等键已用于不同请求。', 409)
                return json.loads(old['response'])
            package['execution_count'] += 1
            db.execute('UPDATE external_skill_packages SET doc=? WHERE id=?', (dumps(package), package['id']))
            db.execute('INSERT INTO external_skill_executions VALUES(?,?,?)',
                       (execution['execution_id'], package['id'], dumps(execution)))
            db.execute('INSERT INTO idempotency VALUES(?,?,?,?)',
                       ('external-skills:execute', key, request_digest, dumps(execution)))
        return execution


def _zip_bytes(manifest_raw, entry_raw):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', manifest_raw)
        archive.writestr('entry.py', entry_raw)
    return output.getvalue()
