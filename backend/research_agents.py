"""Auditable three-role research-agent simulation; never calls a model or network."""
from __future__ import annotations

import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path

from jsonschema import Draft202012Validator

from adapters.research_demo import COMPANIES, ROLES, evaluate, fixture
from .analysis import Problem, digest
from .research import Research
from .service import DENY, ROOT, TERMINAL, TOOLS, local_task, validate
from .store import dumps, now, uid


ENGINE = 'engine_research_multi_agent_simulation'
CONTRACT = json.loads((ROOT / 'specs/v1/research-agent-runtime.schema.json').read_text())
ROLE_SKILLS = {
    'financial': ('research.financial', 'skills/research-financial-analysis/SKILL.md'),
    'industry': ('research.industry', 'skills/research-industry-analysis/SKILL.md'),
    'risk': ('research.risk', 'skills/research-risk-review/SKILL.md'),
}


def validate_contract(kind, value):
    schema = {'$ref': '#/$defs/' + kind, '$defs': CONTRACT['$defs']}
    if list(Draft202012Validator(schema).iter_errors(value)):
        raise Problem('RESEARCH_AGENT_CONTRACT_INVALID', '投研多 Agent 对象不满足机器契约。', 409)


def skill_manifest(role):
    skill_id, relative_path = ROLE_SKILLS[role]
    source = ROOT / relative_path
    if not source.is_file():
        raise Problem('SKILL_UNAVAILABLE', '第一方 Skill 文件不存在。', 409)
    manifest = {
        'id': skill_id,
        'version': '1.0.0',
        'path': relative_path,
        'sha256': digest(source.read_bytes()),
        'mode': 'first_party_local_instruction_only',
        'external_access': False,
    }
    validate_contract('skill_manifest', manifest)
    return manifest


def agent_registry():
    entries = []
    for role in ('financial', 'industry', 'risk'):
        definition = {
            'id': 'research.' + role + '@1',
            'role': role,
            'runtime': 'deterministic_simulation',
            'skill': skill_manifest(role),
            'allowed_tools': ['resource.inspect'],
            'max_turns': 2,
            'model_calls': 0,
            'network_calls': 0,
        }
        validate_contract('agent_definition', definition)
        entries.append(definition)
    return entries


class ResearchToolRuntime:
    """The only child capability.  It never exposes a database or host path."""

    def __init__(self, store):
        self.store = store

    def inspect(self, call, *, assignment, permissions):
        validate_contract('tool_call', call)
        if permissions != ['resource.inspect'] or call['name'] not in permissions:
            raise Problem('FORBIDDEN', '投研 Child Agent 未获 resource.inspect 授权。', 403)
        if call['input']['resource_id'] != assignment['resource_id']:
            raise Problem('RESOURCE_SCOPE_VIOLATION', 'Child Agent 不能读取未分配的资源。', 403)
        resource = self.store.get('resources', assignment['resource_id'])
        raw = self.store.raw(resource['id'])
        if len(raw) > 65536 or digest(raw) != resource['sha256']:
            raise Problem('RESOURCE_INTEGRITY_ERROR', '分配给 Child Agent 的资源不完整或超出限制。', 409)
        observation = {
            'call_id': call['id'],
            'ok': True,
            'resource_id': resource['id'],
            'sha256': resource['sha256'],
            'bytes': len(raw),
            'truncated': False,
        }
        validate_contract('tool_result', observation)
        return raw, observation


class ResearchAgents(Research):
    """A separate vertical slice, deliberately not a Claude SDK adapter."""

    def __init__(self, service):
        super().__init__(service)
        self.tool_runtime = ResearchToolRuntime(self.store)
        # Research's semaphore is intentionally shared with the legacy demo,
        # so all local research work together is bounded to three child runs.
        self.slots = service.research.slots if hasattr(service, 'research') else threading.BoundedSemaphore(3)

    @staticmethod
    def _request_errors(body):
        schema = {'$ref': '#/$defs/research_agent_request', '$defs': CONTRACT['$defs']}
        return list(Draft202012Validator(schema).iter_errors(body))

    def create(self, body, key):
        if self._request_errors(body):
            raise Problem('VALIDATION_ERROR', '投研多 Agent 模拟参数无效。', 422)
        roles = ('financial', 'industry', 'risk')
        child_count = len(body['companies']) * len(roles)
        required_steps = child_count * 2 + 1
        if body['max_steps'] < required_steps:
            raise Problem('BUDGET_EXCEEDED', '需预留每个 Child Agent 两步和父级汇总一步。', 422)

        def create(db):
            registry = agent_registry()
            assignments = []
            for company in body['companies']:
                for role in roles:
                    raw = fixture(company, role, body['scenario'])
                    resource_id = 'res_' + digest(raw)
                    resource = {
                        'id': resource_id,
                        'name': company + '-' + role + '-synthetic.json',
                        'sha256': digest(raw), 'size_bytes': len(raw), 'data_class': 'Public',
                        'row_count': 1, 'columns': [], 'encoding': 'utf-8', 'created_at': now(),
                    }
                    db.execute('INSERT OR IGNORE INTO resources VALUES(?,?,?)', (resource_id, dumps(resource), raw))
                    assignments.append({'company': company, 'role': role, 'resource_id': resource_id})
            task = local_task(assignments[0]['resource_id'], '投研多 Agent 模拟（非真实研报）', body['timeout_seconds'])
            task.update({'id': uid('task'), 'created_at': now(), 'agent_spec_version': 'research_multi_agent_simulation@1'})
            task['context'] = {
                'resource_ids': [item['resource_id'] for item in assignments],
                'variables': {
                    'request': copy.deepcopy(body), 'assignments': assignments,
                    'agent_registry': registry,
                    'runtime': {'id': 'research_agent_simulation@1', 'model_calls': 0, 'provider_calls': 0,
                                'network_calls': 0, 'external_tool_calls': 0},
                },
            }
            task['engine_policy'] = {
                'mode': 'explicit', 'engine_id': ENGINE,
                'required_capabilities': ['actions.tool_call', 'output.structured', 'control.cancel', 'artifacts.files'],
            }
            task['limits']['max_turns'] = body['max_steps']
            task['limits']['max_input_tokens'] = child_count + 1
            validate('task', task)
            db.execute('INSERT INTO tasks VALUES(?,?)', (task['id'], dumps(task)))
            run = self.new_run(db, task)
            return {'task': task, 'initial_run': run}

        return self.service.idempotent('research-agents', key, body, create)

    def new_run(self, db, task, based_on=None):
        assignments = task['context']['variables']['assignments']
        registry = task['context']['variables']['agent_registry']
        if sorted(item['role'] for item in registry) != ['financial', 'industry', 'risk']:
            raise Problem('RESEARCH_AGENT_CONTRACT_INVALID', 'Task 缺少固定三角色 Agent 注册表。', 409)
        runs = self.store.listing('runs')
        if sum(run['status'] not in TERMINAL for run in runs) + len(assignments) + 1 > 32:
            raise Problem('RATE_LIMITED', '本地队列不足以容纳整棵多 Agent 运行树。', 429)
        if based_on and self.store.get('runs', based_on).get('parent_run_id'):
            raise Problem('VALIDATION_ERROR', '多 Agent 重跑只能引用根 Run。', 422)
        attempt = 1 + sum(run['task_id'] == task['id'] and not run.get('parent_run_id') for run in runs)
        policy = {
            'profile_id': 'analysis_read_only', 'profile_version': 1, 'allowed_tools': list(TOOLS),
            'denied_capabilities': list(DENY), 'decision_digest': digest(dumps(task['requested_permissions']).encode()),
        }
        root = {
            'id': uid('run'), 'task_id': task['id'], 'status': 'queued', 'selected_engine': ENGINE,
            'selected_models': {}, 'effective_permissions': policy, 'effective_limits': copy.deepcopy(task['limits']),
            'attempt_number': attempt, 'based_on_run_id': based_on, 'latest_sequence': 0, 'exit_reason': None,
            'created_at': now(), 'updated_at': now(),
        }
        self.insert(db, root, {
            'mode': 'research_agent_simulation@1', 'child_count': len(assignments),
            'reserved_steps': len(assignments) * 2 + 1,
            'agent_registry_digest': digest(dumps(registry).encode()),
            'model_calls': 0, 'provider_calls': 0, 'network_calls': 0,
        })
        by_role = {item['role']: item for item in registry}
        for assignment in assignments:
            child = copy.deepcopy(root)
            child.update({'id': uid('run'), 'parent_run_id': root['id'], 'parent_step_id': uid('step'),
                          'latest_sequence': 0, 'based_on_run_id': None})
            child['effective_permissions']['allowed_tools'] = ['resource.inspect']
            child['effective_permissions']['decision_digest'] = digest(dumps(child['effective_permissions']).encode())
            child['effective_limits']['max_turns'] = 2
            child['effective_limits']['max_input_tokens'] = 1
            self.insert(db, child, {'assignment': assignment, 'agent': by_role[assignment['role']],
                                    'runtime': 'research_agent_simulation@1', 'model_calls': 0, 'network_calls': 0})
            self.store.event(db, root, 'child.created', {
                'child_run_id': child['id'], **assignment, 'agent_id': by_role[assignment['role']]['id'],
                'skill_sha256': by_role[assignment['role']]['skill']['sha256'],
            }, child['parent_step_id'])
        return root

    def _agent(self, child):
        initial = self.store.events(child['id'])[0]['data']
        agent = initial.get('agent')
        if not isinstance(agent, dict):
            raise Problem('RESEARCH_AGENT_CONTRACT_INVALID', 'Child Run 缺少 Agent 快照。', 409)
        validate_contract('agent_definition', agent)
        assignment = initial['assignment']
        if agent['role'] != assignment['role']:
            raise Problem('RESEARCH_AGENT_CONTRACT_INVALID', 'Child Run Agent 角色与分配不一致。', 409)
        current = skill_manifest(agent['role'])
        if current != agent['skill']:
            raise Problem('SKILL_VERSION_MISMATCH', 'Skill 摘要或路径在排队后发生变化。', 409)
        return agent

    def detail(self, root_id):
        with self.store.lock:
            root = self.store.get('runs', root_id)
            if root['selected_engine'] != ENGINE or root.get('parent_run_id'):
                raise Problem('NOT_FOUND', '投研多 Agent 根 Run 不存在。', 404)
            children = []
            for child in self.children(root_id):
                first = self.store.events(child['id'])[0]['data']
                children.append({'run': child, 'assignment': first['assignment'], 'agent': first['agent'],
                                 'artifacts': self.store.artifact_list(child['id'])})
            task = self.store.get('tasks', root['task_id'])
            return {'run': root, 'task': task, 'children': children,
                    'artifacts': self.store.artifact_list(root_id), 'mode': 'research_agent_simulation@1',
                    'real_model': False, 'runtime': task['context']['variables']['runtime']}

    def run_child(self, child_id):
        acquired = False
        tool_step = None
        try:
            while not acquired:
                self.check(child_id)
                acquired = self.slots.acquire(timeout=.05)
            with self.store.transaction() as db:
                self.check(child_id)
                child = self.store.get('runs', child_id)
                if child['status'] != 'queued':
                    return
                parent = self.store.get('runs', child['parent_run_id'])
                if child['effective_permissions']['allowed_tools'] != ['resource.inspect']:
                    raise Problem('FORBIDDEN', 'Child Agent 的工具权限发生扩大或漂移。', 403)
                if not set(child['effective_permissions']['allowed_tools']) <= set(parent['effective_permissions']['allowed_tools']):
                    raise Problem('FORBIDDEN', 'Child Agent 权限超过父 Run。', 403)
                if not set(parent['effective_permissions']['denied_capabilities']) <= set(child['effective_permissions']['denied_capabilities']):
                    raise Problem('FORBIDDEN', 'Child Agent 移除了父 Run 的拒绝项。', 403)
                if child['effective_limits']['max_turns'] != 2 or any(
                    child['effective_limits'][item] > parent['effective_limits'][item]
                    for item in ('timeout_seconds', 'max_input_tokens', 'max_cost_minor')
                ):
                    raise Problem('BUDGET_EXCEEDED', 'Child Agent 预算不满足固定收窄合同。', 422)
                assignment = self.assignment(child)
                agent = self._agent(child)
                child['status'] = 'running'
                self.store.event(db, child, 'run.started', {'mode': 'research_agent_simulation@1'})
                turn_step = uid('step')
                self.store.event(db, child, 'agent.turn.started', {
                    'agent_id': agent['id'], 'turn': 1, 'max_turns': agent['max_turns'], 'model_calls': 0,
                }, turn_step)
                self.store.event(db, child, 'skill.loaded', {
                    'skill_id': agent['skill']['id'], 'version': agent['skill']['version'],
                    'sha256': agent['skill']['sha256'], 'external_access': False,
                }, turn_step)
                call = {'id': uid('call'), 'name': 'resource.inspect', 'input': {'resource_id': assignment['resource_id']}, 'risk': 'read'}
                tool_step = uid('step')
                self.store.event(db, child, 'tool.call.started', {'tool': call['name'], 'call_id': call['id'], 'risk': call['risk']}, tool_step)
            raw, observation = self.tool_runtime.inspect(call, assignment=assignment,
                                                         permissions=child['effective_permissions']['allowed_tools'])
            self.check(child_id)
            result = evaluate(raw, assignment['resource_id'])
            if len(dumps(result).encode()) > 16384 or result != evaluate(raw, assignment['resource_id']):
                raise Problem('RESULT_INVALID', 'Child Agent 输出未通过独立来源回算。', 409)
            with self.store.transaction() as db:
                self.check(child_id)
                child = self.store.get('runs', child_id)
                self.store.event(db, child, 'tool.call.completed', {
                    'tool': call['name'], 'call_id': call['id'], 'steps_used': 1, 'observation_sha256': observation['sha256'],
                }, tool_step)
                self.store.event(db, child, 'agent.observation.received', {
                    'call_id': observation['call_id'], 'resource_id': observation['resource_id'], 'sha256': observation['sha256'],
                    'bytes': observation['bytes'], 'truncated': False,
                }, tool_step)
                artifact = self.publish(db, child, 'agent-result.json', result)
                final_step = uid('step')
                self.store.event(db, child, 'agent.finalized', {
                    'agent_id': agent['id'], 'turn': 2, 'artifact_id': artifact['id'], 'model_calls': 0,
                    'provider_calls': 0, 'network_calls': 0,
                }, final_step)
                self.finish(db, child, 'succeeded', 'COMPLETED')
        except Exception as exc:
            with self.store.transaction() as db:
                child = self.store.get('runs', child_id)
                code = exc.code if isinstance(exc, Problem) else 'INTERNAL_ERROR'
                if tool_step and child['status'] not in TERMINAL:
                    self.store.event(db, child, 'tool.call.failed', {'error_code': code, 'tool': 'resource.inspect'}, tool_step)
                self.finish(db, child, 'failed', code)
        finally:
            if acquired:
                self.slots.release()

    def execute(self, root_id):
        try:
            with self.store.transaction() as db:
                root = self.store.get('runs', root_id)
                if root['status'] != 'queued' or root.get('parent_run_id'):
                    return
                self.check(root_id)
                planned = self.children(root_id)
                if sum(child['effective_limits']['max_turns'] for child in planned) + 1 > root['effective_limits']['max_turns']:
                    raise Problem('BUDGET_EXCEEDED', '父 Run 的步骤预算不足以覆盖 Child Agent 与汇总。', 422)
                root['status'] = 'running'
                self.store.event(db, root, 'run.started', {'mode': 'research_agent_simulation@1', 'model_calls': 0, 'network_calls': 0})
                request = self.store.get('tasks', root['task_id'])['context']['variables']['request']
            children = self.children(root_id)
            with ThreadPoolExecutor(max_workers=request['concurrency'], thread_name_prefix='research-agent-child') as pool:
                pending = {pool.submit(self.run_child, child['id']) for child in children if child['status'] == 'queued'}
                while pending:
                    _, pending = wait(pending, timeout=.05, return_when=FIRST_COMPLETED)
                    self.check(root_id)
                    failed = any(child['status'] in {'failed', 'cancelled', 'expired'} for child in self.children(root_id))
                    if failed and request['failure_policy'] == 'fail_parent':
                        self.fail_tree(root_id, 'CHILD_FAILED')
            self.aggregate(root_id, request)
        except Exception as exc:
            self.fail_tree(root_id, exc.code if isinstance(exc, Problem) else 'INTERNAL_ERROR')

    def aggregate(self, root_id, request):
        with self.store.transaction() as db:
            self.check(root_id)
            root = self.store.get('runs', root_id)
            children = self.children(root_id)
            if any(child['status'] not in TERMINAL for child in children):
                raise Problem('CHILD_INCOMPLETE', '所有 Child Agent 结束后才能汇总。', 409)
            successful = [child for child in children if child['status'] == 'succeeded']
            failed = [child for child in children if child['status'] != 'succeeded']
            if not successful or (failed and request['failure_policy'] == 'fail_parent'):
                self.finish(db, root, 'failed', 'CHILD_FAILED')
                return
            entries = []
            for child in children:
                first = self.store.events(child['id'])[0]['data']
                assignment, agent = first['assignment'], first['agent']
                entry = {'child_run_id': child['id'], **assignment, 'agent_id': agent['id'],
                         'skill': agent['skill'], 'status': child['status'], 'exit_reason': child['exit_reason']}
                artifacts = self.store.artifact_list(child['id'])
                if artifacts:
                    artifact = artifacts[0]
                    body = db.execute('SELECT body FROM artifacts WHERE id=?', (artifact['id'],)).fetchone()[0]
                    if digest(body) != artifact['sha256']:
                        raise Problem('ARTIFACT_INTEGRITY_ERROR', 'Child Agent 产物摘要校验失败。', 409)
                    result = json.loads(body)
                    expected = evaluate(self.store.raw(assignment['resource_id']), assignment['resource_id'])
                    if result != expected:
                        raise Problem('RESULT_INVALID', '父 Run 拒绝未验证的 Child Agent 产物。', 409)
                    entry.update({'artifact_id': artifact['id'], 'sha256': artifact['sha256'], 'summary': result['summary'],
                                  'metrics': result['metrics']})
                entries.append(entry)
            coverage = 'partial' if failed else 'complete'
            manifest = {
                'mode': 'research_agent_simulation@1', 'real_model': False, 'coverage': coverage,
                'root_run_id': root_id, 'children': entries, 'successful': len(successful), 'failed': len(failed),
                'usage': {'model_calls': 0, 'provider_calls': 0, 'network_calls': 0, 'external_tool_calls': 0,
                          'steps_reserved': len(children) * 2 + 1, 'steps_used': len(successful) * 2 + 1},
                'risk_assessment': 'not_assessed',
                'notice': '第一方本地 Skill 与固定模拟循环；不是 Claude SDK、真实金融资料、实时资讯或投资建议。',
            }
            self.publish(db, root, 'research-agent-manifest.json', manifest)
            lines = ['# 投研多 Agent 模拟报告', '', manifest['notice'], '', '覆盖：' + coverage,
                     '风险状态：未评估；资料缺失或模拟资料不能解释为无风险。', '']
            for entry in entries:
                lines.extend(['## ' + COMPANIES[entry['company']] + ' / ' + ROLES[entry['role']],
                              'Agent: ' + entry['agent_id'], 'Skill SHA-256: ' + entry['skill']['sha256'],
                              entry.get('summary', '未获得有效结果：' + str(entry['exit_reason'])),
                              'Child Run: ' + entry['child_run_id'], '来源资源: ' + entry['resource_id'], ''])
            self.publish(db, root, 'research-agent-report.md', '\n'.join(lines), 'text/markdown')
            self.store.event(db, root, 'research.agent.aggregated', {
                'coverage': coverage, 'successful': len(successful), 'failed': len(failed),
                'model_calls': 0, 'network_calls': 0,
            })
            self.finish(db, root, 'succeeded', 'COMPLETED_WITH_WARNINGS' if failed else 'COMPLETED')

    def recover(self):
        """A restart closes this engine's entire running tree before the worker starts."""
        for root in self.store.listing('runs'):
            if root['selected_engine'] != ENGINE or root.get('parent_run_id'):
                continue
            children = self.children(root['id'])
            if root['status'] == 'running' or any(child['status'] == 'running' for child in children):
                self.fail_tree(root['id'], 'SERVER_RESTARTED')
