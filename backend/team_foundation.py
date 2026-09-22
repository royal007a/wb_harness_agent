"""Local Workspace / Agent identity / Channel protocol boundary.

This module deliberately persists *protocol* identities only.  An ``actor_id``
in an HTTP request is not a signed user session, a Provider identity, or a
runtime principal.  It is nevertheless useful to make the local control plane
checkable before Inbox, message delivery or any Agent runtime is introduced.
"""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .analysis import Problem, digest
from .store import dumps, now
from .team_security import reject_sensitive


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'specs/v1/team-foundation.schema.json').read_text())
CLASS_RANK = {'Public': 0, 'Internal': 1, 'Restricted': 2}
ADMIN_ROLES = {'owner', 'admin'}


def validate_contract(name, value):
    schema = {'$ref': '#/$defs/' + name, '$defs': CONTRACT['$defs']}
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise Problem('TEAM_FOUNDATION_CONTRACT_INVALID', '请求不满足 Team Foundation 契约。', 422)


class TeamFoundation:
    """Durable local protocol-authorisation records, with no auth provider."""

    def __init__(self, store):
        self.store = store
        self._ensure_bootstrap()

    @staticmethod
    def runtime_status():
        return {
            'mode': 'team_foundation_boundary@1',
            'protocol_identity_authentication': 'not_connected',
            'agent_runtime': 'not_connected',
            'external_model_calls': 0,
            'external_tool_calls': 0,
            'message_delivery': 'not_implemented',
            'note': ('只保存本机协议身份、成员关系与 Channel 数据边界；actor_id 不是登录或签名身份，'
                     '不会启动模型、工具、消息、Inbox、Daemon 或自动审批。'),
        }

    def _ensure_bootstrap(self):
        """Create only the local-admin bootstrap principal and local workspace."""
        with self.store.transaction() as db:
            created_at = now()
            admin = {
                'schema_version': 'agent-identity@1', 'id': 'local_admin', 'kind': 'human',
                'display_name': 'Local Admin', 'status': 'active', 'created_at': created_at,
            }
            workspace = {
                'schema_version': 'team-workspace@1', 'id': 'ws_local', 'name': 'Local Harness Workspace',
                'data_class': 'Restricted', 'status': 'active', 'created_by_id': 'local_admin',
                'created_at': created_at,
            }
            membership = {
                'schema_version': 'workspace-membership@1', 'workspace_id': 'ws_local',
                'agent_id': 'local_admin', 'role': 'owner', 'clearance': 'Restricted',
                'status': 'active', 'created_at': created_at,
            }
            for kind, value in (('agent_identity', admin), ('workspace', workspace),
                                ('workspace_membership', membership)):
                validate_contract(kind, value)
            db.execute('INSERT OR IGNORE INTO team_agent_identities VALUES(?,?)', (admin['id'], dumps(admin)))
            db.execute('INSERT OR IGNORE INTO team_workspaces VALUES(?,?)', (workspace['id'], dumps(workspace)))
            db.execute('INSERT OR IGNORE INTO team_workspace_memberships VALUES(?,?,?)',
                       (membership['workspace_id'], membership['agent_id'], dumps(membership)))

    @staticmethod
    def _idempotency_key(key):
        if not isinstance(key, str) or not 1 <= len(key) <= 128:
            raise Problem('VALIDATION_ERROR', '必须提供 1–128 字符的 Idempotency-Key。', 422)

    def _idempotent(self, scope, key, body, action):
        self._idempotency_key(key)
        request_digest = digest(dumps(body).encode())
        with self.store.transaction() as db:
            old = db.execute('SELECT digest,response FROM idempotency WHERE scope=? AND key=?', (scope, key)).fetchone()
            if old:
                if old['digest'] != request_digest:
                    raise Problem('CONFLICT', '同一幂等键已用于不同请求。', 409)
                return json.loads(old['response'])
            result = action(db)
            db.execute('INSERT INTO idempotency VALUES(?,?,?,?)', (scope, key, request_digest, dumps(result)))
            return result

    @staticmethod
    def _row(db, table, ident, error_code, message):
        row = db.execute(f'SELECT doc FROM {table} WHERE id=?', (ident,)).fetchone()
        if not row:
            raise Problem(error_code, message, 404)
        return json.loads(row['doc'])

    def _agent(self, db, agent_id):
        agent = self._row(db, 'team_agent_identities', agent_id, 'TEAM_AGENT_NOT_FOUND', 'Agent Identity 不存在。')
        if agent['status'] != 'active':
            raise Problem('TEAM_AGENT_SUSPENDED', 'Agent Identity 已暂停。', 403)
        return agent

    def _workspace(self, db, workspace_id):
        workspace = self._row(db, 'team_workspaces', workspace_id, 'TEAM_WORKSPACE_NOT_FOUND', 'Workspace 不存在。')
        if workspace['status'] != 'active':
            raise Problem('TEAM_WORKSPACE_ARCHIVED', 'Workspace 已归档。', 409)
        return workspace

    def _channel(self, db, channel_id):
        channel = self._row(db, 'team_channels', channel_id, 'TEAM_CHANNEL_NOT_FOUND', 'Channel 不存在。')
        if channel['status'] != 'active':
            raise Problem('TEAM_CHANNEL_ARCHIVED', 'Channel 已归档。', 409)
        return channel

    def _workspace_membership(self, db, workspace_id, agent_id):
        row = db.execute('SELECT doc FROM team_workspace_memberships WHERE workspace_id=? AND agent_id=?',
                         (workspace_id, agent_id)).fetchone()
        if not row:
            raise Problem('TEAM_WORKSPACE_ACCESS_DENIED', '该 Agent 没有此 Workspace 的访问资格。', 403)
        membership = json.loads(row['doc'])
        if membership['status'] != 'active':
            raise Problem('TEAM_WORKSPACE_ACCESS_DENIED', '该 Workspace membership 已撤销。', 403)
        return membership

    def _channel_membership(self, db, channel_id, agent_id):
        row = db.execute('SELECT doc FROM team_channel_memberships WHERE channel_id=? AND agent_id=?',
                         (channel_id, agent_id)).fetchone()
        if not row:
            raise Problem('TEAM_CHANNEL_ACCESS_DENIED', '该 Agent 没有此 Channel 的访问资格。', 403)
        membership = json.loads(row['doc'])
        if membership['status'] != 'active':
            raise Problem('TEAM_CHANNEL_ACCESS_DENIED', '该 Channel membership 已撤销。', 403)
        return membership

    @staticmethod
    def _dominates(clearance, data_class):
        return CLASS_RANK[clearance] >= CLASS_RANK[data_class]

    def _assert_workspace_admin(self, db, workspace_id, actor_id):
        self._agent(db, actor_id)
        workspace = self._workspace(db, workspace_id)
        membership = self._workspace_membership(db, workspace_id, actor_id)
        if membership['role'] not in ADMIN_ROLES:
            raise Problem('TEAM_WORKSPACE_ADMIN_REQUIRED', '只有 Workspace owner 或 admin 可以管理成员和 Channel。', 403)
        if not self._dominates(membership['clearance'], workspace['data_class']):
            raise Problem('TEAM_DATA_CLEARANCE_DENIED', '成员 clearance 不满足 Workspace 数据等级。', 403)
        return workspace, membership

    def assert_channel_access(self, db, channel_id, actor_id, required_roles=None):
        """Check all three scopes: identity, Workspace/data class, Channel role."""
        self._agent(db, actor_id)
        channel = self._channel(db, channel_id)
        workspace = self._workspace(db, channel['workspace_id'])
        membership = self._workspace_membership(db, workspace['id'], actor_id)
        if not self._dominates(membership['clearance'], channel['data_class']):
            raise Problem('TEAM_DATA_CLEARANCE_DENIED', '成员 clearance 不满足 Channel 数据等级。', 403)
        channel_membership = self._channel_membership(db, channel_id, actor_id)
        if required_roles and not set(channel_membership['roles']).intersection(required_roles):
            raise Problem('TEAM_CHANNEL_ROLE_DENIED', '该 Channel role 不允许此操作。', 403)
        return workspace, channel, membership, channel_membership

    def assert_task_access(self, db, task, actor_id, required_roles=None):
        if task.get('schema_version') != 'team-task@2':
            raise Problem('TEAM_TASK_LEGACY_UNBOUND', '历史 Team Task 未绑定新的 Workspace/Channel 身份边界，不能自动访问或操作。', 409)
        workspace, channel, membership, channel_membership = self.assert_channel_access(
            db, task['channel_id'], actor_id, required_roles)
        if workspace['id'] != task['workspace_id']:
            raise Problem('TEAM_TASK_SCOPE_INVALID', 'Task 的 Workspace 与 Channel 不一致。', 409)
        return workspace, channel, membership, channel_membership

    def create_workspace(self, body, key):
        validate_contract('workspace_create_request', body)
        reject_sensitive(body)

        def create(db):
            # There is intentionally only one bootstrap platform owner until a
            # real authenticated platform-administration layer is admitted.
            if body['actor_id'] != 'local_admin':
                raise Problem('TEAM_BOOTSTRAP_ADMIN_REQUIRED', '当前仅 local_admin 可以创建 Workspace。', 403)
            self._agent(db, body['actor_id'])
            if db.execute('SELECT 1 FROM team_workspaces WHERE id=?', (body['id'],)).fetchone():
                raise Problem('CONFLICT', 'Workspace ID 已存在。', 409)
            created_at = now()
            workspace = {
                'schema_version': 'team-workspace@1', 'id': body['id'], 'name': body['name'],
                'data_class': body['data_class'], 'status': 'active', 'created_by_id': body['actor_id'],
                'created_at': created_at,
            }
            membership = {
                'schema_version': 'workspace-membership@1', 'workspace_id': workspace['id'],
                'agent_id': body['actor_id'], 'role': 'owner', 'clearance': 'Restricted',
                'status': 'active', 'created_at': created_at,
            }
            validate_contract('workspace', workspace)
            validate_contract('workspace_membership', membership)
            db.execute('INSERT INTO team_workspaces VALUES(?,?)', (workspace['id'], dumps(workspace)))
            db.execute('INSERT INTO team_workspace_memberships VALUES(?,?,?)',
                       (workspace['id'], body['actor_id'], dumps(membership)))
            return workspace
        return self._idempotent('team-foundation:workspace:create', key, body, create)

    def create_agent(self, workspace_id, body, key):
        validate_contract('agent_create_request', body)
        reject_sensitive(body)
        if body['workspace_id'] != workspace_id:
            raise Problem('TEAM_WORKSPACE_SCOPE_INVALID', '请求 Workspace 与路径不一致。', 409)

        def create(db):
            workspace, _ = self._assert_workspace_admin(db, workspace_id, body['actor_id'])
            if db.execute('SELECT 1 FROM team_agent_identities WHERE id=?', (body['id'],)).fetchone():
                raise Problem('CONFLICT', 'Agent Identity ID 已存在；请使用 Workspace membership 接入已有身份。', 409)
            created_at = now()
            agent = {
                'schema_version': 'agent-identity@1', 'id': body['id'], 'kind': body['kind'],
                'display_name': body['display_name'], 'status': 'active', 'created_at': created_at,
            }
            membership = {
                'schema_version': 'workspace-membership@1', 'workspace_id': workspace_id,
                'agent_id': body['id'], 'role': 'member', 'clearance': body['clearance'],
                'status': 'active', 'created_at': created_at,
            }
            validate_contract('agent_identity', agent)
            validate_contract('workspace_membership', membership)
            db.execute('INSERT INTO team_agent_identities VALUES(?,?)', (agent['id'], dumps(agent)))
            db.execute('INSERT INTO team_workspace_memberships VALUES(?,?,?)',
                       (workspace_id, agent['id'], dumps(membership)))
            return {'agent': agent, 'membership': membership}
        return self._idempotent('team-foundation:' + workspace_id + ':agent:create', key, body, create)

    def grant_workspace_membership(self, workspace_id, body, key):
        validate_contract('workspace_membership_grant_request', body)
        reject_sensitive(body)

        def grant(db):
            workspace, _ = self._assert_workspace_admin(db, workspace_id, body['actor_id'])
            self._agent(db, body['agent_id'])
            old = db.execute('SELECT 1 FROM team_workspace_memberships WHERE workspace_id=? AND agent_id=?',
                             (workspace_id, body['agent_id'])).fetchone()
            if old:
                raise Problem('CONFLICT', '该 Agent 已是 Workspace 成员。', 409)
            membership = {
                'schema_version': 'workspace-membership@1', 'workspace_id': workspace_id,
                'agent_id': body['agent_id'], 'role': body['role'], 'clearance': body['clearance'],
                'status': 'active', 'created_at': now(),
            }
            validate_contract('workspace_membership', membership)
            db.execute('INSERT INTO team_workspace_memberships VALUES(?,?,?)',
                       (workspace_id, body['agent_id'], dumps(membership)))
            return membership
        return self._idempotent('team-foundation:' + workspace_id + ':membership:grant', key, body, grant)

    def create_channel(self, workspace_id, body, key):
        validate_contract('channel_create_request', body)
        reject_sensitive(body)

        def create(db):
            workspace, actor_membership = self._assert_workspace_admin(db, workspace_id, body['actor_id'])
            if not self._dominates(workspace['data_class'], body['data_class']):
                raise Problem('TEAM_CHANNEL_DATA_CLASS_INVALID', 'Channel 数据等级不能高于所属 Workspace。', 422)
            if not self._dominates(actor_membership['clearance'], body['data_class']):
                raise Problem('TEAM_DATA_CLEARANCE_DENIED', '创建者 clearance 不满足 Channel 数据等级。', 403)
            if db.execute('SELECT 1 FROM team_channels WHERE id=?', (body['id'],)).fetchone():
                raise Problem('CONFLICT', 'Channel ID 已存在。', 409)
            created_at = now()
            channel = {
                'schema_version': 'team-channel@1', 'id': body['id'], 'workspace_id': workspace_id,
                'title': body['title'], 'data_class': body['data_class'], 'status': 'active',
                'created_by_id': body['actor_id'], 'version': 1, 'created_at': created_at, 'updated_at': created_at,
            }
            membership = {
                'schema_version': 'channel-membership@1', 'channel_id': body['id'], 'agent_id': body['actor_id'],
                'roles': ['coordinator'], 'status': 'active', 'created_at': created_at,
            }
            validate_contract('channel', channel)
            validate_contract('channel_membership', membership)
            db.execute('INSERT INTO team_channels VALUES(?,?,?)', (channel['id'], workspace_id, dumps(channel)))
            db.execute('INSERT INTO team_channel_memberships VALUES(?,?,?)',
                       (channel['id'], body['actor_id'], dumps(membership)))
            return {'channel': channel, 'membership': membership}
        return self._idempotent('team-foundation:' + workspace_id + ':channel:create', key, body, create)

    def grant_channel_membership(self, channel_id, body, key):
        validate_contract('channel_membership_grant_request', body)
        reject_sensitive(body)

        def grant(db):
            channel = self._channel(db, channel_id)
            self._assert_workspace_admin(db, channel['workspace_id'], body['actor_id'])
            self._agent(db, body['agent_id'])
            target = self._workspace_membership(db, channel['workspace_id'], body['agent_id'])
            if not self._dominates(target['clearance'], channel['data_class']):
                raise Problem('TEAM_DATA_CLEARANCE_DENIED', '目标成员 clearance 不满足 Channel 数据等级。', 403)
            old = db.execute('SELECT 1 FROM team_channel_memberships WHERE channel_id=? AND agent_id=?',
                             (channel_id, body['agent_id'])).fetchone()
            if old:
                raise Problem('CONFLICT', '该 Agent 已是 Channel 成员。', 409)
            membership = {
                'schema_version': 'channel-membership@1', 'channel_id': channel_id, 'agent_id': body['agent_id'],
                'roles': body['roles'], 'status': 'active', 'created_at': now(),
            }
            validate_contract('channel_membership', membership)
            db.execute('INSERT INTO team_channel_memberships VALUES(?,?,?)',
                       (channel_id, body['agent_id'], dumps(membership)))
            return membership
        return self._idempotent('team-foundation:' + channel_id + ':membership:grant', key, body, grant)

    def workspaces(self, actor_id):
        with self.store.transaction() as db:
            self._agent(db, actor_id)
            rows = db.execute('SELECT w.doc AS workspace_doc,m.doc AS membership_doc FROM team_workspaces w '
                              'JOIN team_workspace_memberships m ON w.id=m.workspace_id WHERE m.agent_id=? '
                              'ORDER BY w.id', (actor_id,)).fetchall()
            items = []
            for row in rows:
                workspace, membership = json.loads(row['workspace_doc']), json.loads(row['membership_doc'])
                if workspace['status'] == 'active' and membership['status'] == 'active':
                    items.append(workspace)
            return {'items': items, 'runtime': self.runtime_status()}

    def workspace_detail(self, workspace_id, actor_id):
        with self.store.transaction() as db:
            self._agent(db, actor_id)
            workspace = self._workspace(db, workspace_id)
            self._workspace_membership(db, workspace_id, actor_id)
            memberships = [json.loads(row['doc']) for row in db.execute(
                'SELECT doc FROM team_workspace_memberships WHERE workspace_id=? ORDER BY rowid', (workspace_id,)).fetchall()]
            result = {'workspace': workspace, 'memberships': memberships}
            validate_contract('workspace_detail', result)
            return result

    def agents(self, workspace_id, actor_id):
        with self.store.transaction() as db:
            self._agent(db, actor_id)
            self._workspace(db, workspace_id)
            self._workspace_membership(db, workspace_id, actor_id)
            rows = db.execute('SELECT a.doc FROM team_agent_identities a JOIN team_workspace_memberships m '
                              'ON a.id=m.agent_id WHERE m.workspace_id=? ORDER BY a.id', (workspace_id,)).fetchall()
            return {'items': [json.loads(row['doc']) for row in rows], 'runtime': self.runtime_status()}

    def channels(self, workspace_id, actor_id):
        with self.store.transaction() as db:
            self._agent(db, actor_id)
            self._workspace(db, workspace_id)
            self._workspace_membership(db, workspace_id, actor_id)
            rows = db.execute('SELECT c.doc FROM team_channels c JOIN team_channel_memberships m '
                              'ON c.id=m.channel_id WHERE c.workspace_id=? AND m.agent_id=? ORDER BY c.rowid DESC',
                              (workspace_id, actor_id)).fetchall()
            return {'items': [json.loads(row['doc']) for row in rows], 'runtime': self.runtime_status()}

    def channel_detail(self, channel_id, actor_id):
        with self.store.transaction() as db:
            _, channel, _, _ = self.assert_channel_access(db, channel_id, actor_id)
            memberships = [json.loads(row['doc']) for row in db.execute(
                'SELECT doc FROM team_channel_memberships WHERE channel_id=? ORDER BY rowid', (channel_id,)).fetchall()]
            result = {'channel': channel, 'memberships': memberships}
            validate_contract('channel_detail', result)
            return result
