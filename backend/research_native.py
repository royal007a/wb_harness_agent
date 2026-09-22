"""Product Run integration for the native, configuration-gated Claude research adapter."""
from __future__ import annotations

import asyncio
import copy
from dataclasses import asdict
import json
import re
from pathlib import Path
from typing import Any

from adapters.claude_research import (
    RUNTIME_MODE, SOURCE_TOOL_NAMES, configuration_from_request,
    runtime_status, stream_native_research, validate_contract,
)
from .agent_runtime import KeyringCredentialResolver
from .analysis import Problem, digest
from .research import Research
from .research_sources import ResearchSourceGateway, policy_from_env
from .service import DENY, ROOT, TERMINAL, local_task, validate
from .store import dumps, now, uid


ENGINE = 'engine_claude_research_native'
ROLES = ('financial', 'industry', 'risk')
SOURCE_IDS = re.compile(r'\bsrc_[A-Za-z0-9]+\b')


class NativeResearch(Research):
    """One native parent query creates and audits three SDK-owned Child Runs.

    The parent SDK owns subagent scheduling. The control plane never claims a
    child was concurrent merely because three child rows exist; the SDK event
    trace must show all three `Agent` delegations for a successful parent Run.
    """

    def create(self, body, key):
        validate_contract('native_research_request', body)
        config = configuration_from_request(body)
        # Deliberately fail before any task row or model/HTTP activity if the
        # approval/configuration gates are incomplete.
        from adapters.claude_research import assert_ready
        assert_ready(config)
        policy = policy_from_env()
        if not policy.enabled:
            raise Problem('EXTERNAL_DATA_RUNTIME_DISABLED', '外部资料工具未获启动许可。', 409)
        resource = self.store.get('resources', body['report_resource_id'])
        raw = self.store.raw(resource['id'])
        if resource.get('data_class') != 'Public' or not resource.get('name', '').lower().endswith('.pdf') or not raw.startswith(b'%PDF-'):
            raise Problem('PDF_RESOURCE_INVALID', '原生投研只接受已登记、Public 的 PDF 财报资料。', 422)
        if digest(raw) != resource['sha256']:
            raise Problem('RESOURCE_INTEGRITY_ERROR', '财报 PDF 摘要不匹配。', 409)

        def create(db):
            task = local_task(resource['id'], body['objective'], body['timeout_seconds'])
            task.update({
                'id': uid('task'), 'created_at': now(), 'agent_spec_version': 'claude_native_research@1',
                'context': {'resource_ids': [resource['id']], 'variables': {
                    'request': copy.deepcopy(body), 'runtime_configuration': runtime_status(),
                    'source_policy_digest': digest(dumps(asdict(policy)).encode()),
                    'plugin_mode': 'local_first_party_plugin_only',
                }},
                'engine_policy': {'mode': 'explicit', 'engine_id': ENGINE,
                                  'required_capabilities': ['actions.subagent', 'actions.tool_call', 'sources.read', 'artifacts.files', 'control.cancel']},
                'model_policy': {'text_and_code': config.model, 'vision': None, 'allow_fallback': False},
                'requested_permissions': {'profile': 'analysis_read_only', 'profile_version': 1,
                                          'allow_tools': ['Agent', *sorted({tool for tools in SOURCE_TOOL_NAMES.values() for tool in tools})],
                                          'deny_capabilities': list(DENY)},
                'limits': {'max_turns': config.max_turns, 'timeout_seconds': body['timeout_seconds'],
                           'max_input_tokens': 12000, 'max_cost_minor': body['max_cost_minor']},
            })
            validate('task', task)
            db.execute('INSERT INTO tasks VALUES(?,?)', (task['id'], dumps(task)))
            run = self.new_run(db, task)
            return {'task': task, 'initial_run': run}
        return self.service.idempotent('research-native', key, body, create)

    def cancel(self, run_id):
        """Cancel the whole native SDK run tree even when a Child is selected.

        The SDK query runs in the worker, so this durable cancellation marker
        is observed before every subsequent persisted SDK event.  Exiting the
        async iterator then asks the SDK transport to close.  A live L3 probe
        must verify that the provider/CLI actually stops its background work.
        """
        with self.store.transaction() as db:
            selected = self.store.get('runs', run_id)
            root_id = selected.get('parent_run_id') or selected['id']
            root = self.store.get('runs', root_id)
            if root['selected_engine'] != ENGINE:
                raise Problem('NOT_FOUND', '原生投研 Run 不存在。', 404)
            if root['status'] in TERMINAL:
                return root
            for child in self.children(root_id):
                self.finish(db, child, 'cancelled', 'PARENT_CANCELLED')
            self.finish(db, root, 'cancelled', 'USER_CANCELLED')
            self.store.event(db, root, 'research.native.cancel.requested', {
                'requested_run_id': run_id,
                'sdk_transport_outcome': 'pending_l3_probe',
            })
            return root

    def new_run(self, db, task, based_on=None):
        if based_on:
            source = self.store.get('runs', based_on)
            if source.get('parent_run_id') or source['selected_engine'] != ENGINE:
                raise Problem('VALIDATION_ERROR', '原生投研只能从同引擎父 Run 重跑。', 422)
        active = [run for run in self.store.listing('runs') if run['status'] not in TERMINAL]
        if len(active) + 4 > 32:
            raise Problem('RATE_LIMITED', '本地队列不足以容纳原生投研运行树。', 429)
        request = task['context']['variables']['request']
        config = configuration_from_request(request)
        registry = runtime_status()
        if registry != task['context']['variables']['runtime_configuration']:
            raise Problem('RUNTIME_CONFIGURATION_DRIFT', '原生投研运行时配置在排队后发生变化。', 409)
        attempt = 1 + sum(run['task_id'] == task['id'] and not run.get('parent_run_id') for run in self.store.listing('runs'))
        root = {
            'id': uid('run'), 'task_id': task['id'], 'status': 'queued', 'selected_engine': ENGINE,
            'selected_models': {'text_and_code': config.model or ''},
            'effective_permissions': {'profile_id': 'analysis_read_only', 'profile_version': 1, 'allowed_tools': ['Agent'],
                                      'denied_capabilities': list(DENY),
                                      'decision_digest': digest(dumps(task['requested_permissions']).encode())},
            'effective_limits': copy.deepcopy(task['limits']), 'attempt_number': attempt, 'based_on_run_id': based_on,
            'latest_sequence': 0, 'exit_reason': None, 'created_at': now(), 'updated_at': now(),
        }
        self.insert(db, root, {'mode': RUNTIME_MODE, 'runtime_configuration': registry,
                               'plugin_mode': 'local_first_party_plugin_only', 'child_count': 3,
                               'model_calls': 0, 'network_calls': 0})
        for role in ROLES:
            child = copy.deepcopy(root)
            child.update({'id': uid('run'), 'parent_run_id': root['id'], 'parent_step_id': uid('step'), 'based_on_run_id': None,
                          'latest_sequence': 0, 'selected_models': {'text_and_code': config.model or ''}})
            child['effective_permissions']['allowed_tools'] = list(SOURCE_TOOL_NAMES[role])
            child['effective_permissions']['decision_digest'] = digest(dumps(child['effective_permissions']).encode())
            child['effective_limits']['max_turns'] = 4
            child['effective_limits']['max_input_tokens'] = 4000
            child['effective_limits']['max_cost_minor'] = task['limits']['max_cost_minor'] // len(ROLES)
            self.insert(db, child, {'role': role, 'sdk_agent_name': role, 'skill': 'research-skills:' + {
                'financial': 'financial-analysis', 'industry': 'industry-analysis', 'risk': 'risk-review'}[role],
                'sdk_runtime': RUNTIME_MODE, 'status_origin': 'awaiting_native_agent_delegation'})
            self.store.event(db, root, 'child.created', {'child_run_id': child['id'], 'role': role,
                                                         'allowed_tools': list(SOURCE_TOOL_NAMES[role])}, child['parent_step_id'])
        return root

    def detail(self, root_id):
        root = self.store.get('runs', root_id)
        if root['selected_engine'] != ENGINE or root.get('parent_run_id'):
            raise Problem('NOT_FOUND', '原生投研根 Run 不存在。', 404)
        task = self.store.get('tasks', root['task_id'])
        return {'run': root, 'task': task, 'children': [
            {'run': child, 'role': self._role(child), 'artifacts': self.store.artifact_list(child['id'])}
            for child in self.children(root_id)], 'artifacts': self.store.artifact_list(root_id),
            'mode': RUNTIME_MODE, 'runtime': runtime_status(), 'real_model': True}

    def _role(self, child) -> str:
        initial = self.store.events(child['id'])[0]['data']
        role = initial.get('role')
        if role not in ROLES:
            raise Problem('CLAUDE_RESEARCH_CONTRACT_INVALID', '原生 Child Run 缺少固定角色。', 409)
        return role

    def _pdf_loader(self, expected_id):
        def load(resource_id):
            if resource_id != expected_id:
                raise Problem('RESOURCE_SCOPE_VIOLATION', 'PDF 工具只能读取该 Run 已绑定的财报资源。', 403)
            document = self.store.get('resources', resource_id)
            raw = self.store.raw(resource_id)
            if digest(raw) != document['sha256']:
                raise Problem('RESOURCE_INTEGRITY_ERROR', 'PDF 资源摘要不匹配。', 409)
            return document, raw
        return load

    @staticmethod
    def _prompt(task):
        request = task['context']['variables']['request']
        return (
            '研究目标：' + request['objective'] + '\n'
            '公司：' + request['company'] + '；股票代码：' + request['stock_code'] + '\n'
            '已登记财报 PDF 资源：' + request['report_resource_id'] + '\n\n'
            '必须在同一轮委派且只委派以下三个 SubAgent：financial、industry、risk。'
            '它们可并发，不能由父 Agent 自己检索或分析。每个 Child 最终输出需使用 source_id 标注事实，'
            '资料不足必须写“未评估”。收到三个结果后，父 Agent 输出一个短 Markdown 汇总，区分事实、推断、冲突和缺口；'
            '不得给出投资建议、交易意见、ST/退市预测或价格预测。'
        )

    def _emit_sdk_event(self, root_id, event, delegation, child_text):
        """Persist an SDK observation to its parent or delegated Child Run."""
        target = root_id
        payload = copy.deepcopy(event['payload'])
        if event['kind'] == 'assistant.tool_use' and event['agent_scope'] == 'parent' and payload.get('tool') == 'Agent':
            # The normalizer intentionally does not persist arbitrary input;
            # subagent_type is the one fixed, non-secret routing field.
            role = payload.get('subagent_type')
            if role in ROLES and role not in delegation.values():
                delegation[payload['tool_use_id']] = role
                child = next(item for item in self.children(root_id) if self._role(item) == role)
                with self.store.transaction() as db:
                    current = self.store.get('runs', child['id'])
                    if current['status'] == 'queued':
                        current['status'] = 'running'
                        self.store.event(db, current, 'run.started', {'origin': 'native_sdk_agent'})
                    root = self.store.get('runs', root_id)
                    self.store.event(db, root, 'agent.delegated', {'child_run_id': child['id'], 'role': role,
                                                                   'sdk_tool_use_id': payload['tool_use_id']})
                return
        if event['agent_scope'] == 'child':
            role = delegation.get(event['parent_tool_use_id'])
            if role:
                target = next(item['id'] for item in self.children(root_id) if self._role(item) == role)
        if event['kind'] == 'assistant.text':
            child_text.setdefault(target, []).append(payload.get('text', ''))
        event_type = {
            'assistant.text': 'agent.sdk.text', 'assistant.tool_use': 'agent.sdk.tool_use',
            'assistant.tool_result': 'agent.sdk.tool_result', 'sdk.system': 'agent.sdk.system',
            'sdk.result': 'agent.sdk.result', 'sdk.rate_limit': 'agent.sdk.rate_limit',
        }[event['kind']]
        with self.store.transaction() as db:
            run = self.store.get('runs', target)
            self.check(root_id)
            if target != root_id:
                self.check(target)
            self.store.event(db, run, event_type, payload)

    def execute(self, root_id):
        try:
            with self.store.transaction() as db:
                root = self.store.get('runs', root_id)
                if root['selected_engine'] != ENGINE or root.get('parent_run_id') or root['status'] != 'queued':
                    return
                self.check(root_id)
                root['status'] = 'running'
                self.store.event(db, root, 'run.started', {'mode': RUNTIME_MODE})
                task = self.store.get('tasks', root['task_id'])
            request = task['context']['variables']['request']
            config = configuration_from_request(request)
            if runtime_status() != task['context']['variables']['runtime_configuration']:
                raise Problem('RUNTIME_CONFIGURATION_DRIFT', '原生投研运行时配置发生变化。', 409)
            policy = policy_from_env()
            if digest(dumps(asdict(policy)).encode()) != task['context']['variables']['source_policy_digest']:
                raise Problem('SOURCE_POLICY_DRIFT', '资料源配置在排队后发生变化。', 409)
            # Source credential references are intentionally resolved only
            # inside the source gateway at an actual HTTP boundary.  Creating
            # or queueing a Run therefore never reads the operating-system
            # Keychain, while a configured real source can still authenticate
            # without putting a secret in a Task, prompt, event or artifact.
            gateway = ResearchSourceGateway(
                policy,
                credential_resolver=KeyringCredentialResolver(),
                pdf_loader=self._pdf_loader(request['report_resource_id']),
            )
            delegation: dict[str, str] = {}
            child_text: dict[str, list[str]] = {}

            async def collect():
                async for event in stream_native_research(self._prompt(task), config, gateway):
                    self._emit_sdk_event(root_id, event, delegation, child_text)
            asyncio.run(collect())
            self._aggregate(root_id, delegation, child_text, gateway.evidence, request)
        except Exception as exc:
            self.fail_tree(root_id, exc.code if isinstance(exc, Problem) else 'CLAUDE_RESEARCH_INTERNAL_ERROR')

    def _aggregate(self, root_id, delegation, child_text, evidence, request):
        with self.store.transaction() as db:
            root = self.store.get('runs', root_id)
            if root['status'] in TERMINAL:
                return
            missing = [role for role in ROLES if role not in delegation.values()]
            if missing:
                raise Problem('SUBAGENT_NOT_INVOKED', 'SDK 未委派所有固定 SubAgent：' + ','.join(missing), 409)
            entries = []
            for child in self.children(root_id):
                role = self._role(child)
                current = self.store.get('runs', child['id'])
                text = '\n'.join(child_text.get(child['id'], [])).strip()
                cited = sorted(set(SOURCE_IDS.findall(text)))
                if any(source_id not in evidence for source_id in cited):
                    raise Problem('UNVERIFIED_SOURCE_REFERENCE', 'Child 引用了不存在的 source_id。', 409)
                if not cited and '未评估' not in text:
                    raise Problem('CHILD_EVIDENCE_MISSING', 'Child 没有来源证据时必须明确未评估。', 409)
                if current['status'] == 'queued':
                    raise Problem('SUBAGENT_EVENT_MISSING', 'Child 未产生可审计的 SDK 事件。', 409)
                body = text or '未评估：Native SDK Child 未返回可审计文本。'
                artifact = self.publish(db, current, role + '-native-report.md', body, 'text/markdown')
                self.finish(db, current, 'succeeded', 'COMPLETED' if cited else 'COMPLETED_WITH_UNASSESSED_GAPS')
                entries.append({'role': role, 'child_run_id': current['id'], 'artifact_id': artifact['id'],
                                'source_ids': cited, 'status': current['status']})
            source_entries = [evidence[source_id] for source_id in sorted(evidence)]
            # This is an audit mapping, not a concurrency claim.  The SDK
            # trace supplies event timestamps for the L3 reviewer to verify
            # actual overlap after the requested background execution.
            delegation_entries = [
                {'sdk_tool_use_id': tool_use_id, 'role': role}
                for tool_use_id, role in sorted(delegation.items())
            ]
            manifest = {'mode': RUNTIME_MODE, 'real_model': True, 'root_run_id': root_id, 'company': request['company'],
                        'stock_code': request['stock_code'], 'children': entries, 'source_evidence': source_entries,
                        'background_execution_requested': True, 'delegations': delegation_entries,
                        'coverage': 'complete' if all(item['source_ids'] for item in entries) else 'partial',
                        'notice': '模型文字仅为带来源证据的研究草稿；未评估不代表无风险，禁止作为投资建议。背景执行请求不等于实际并发，须核验 SDK 事件时间线。'}
            self.publish(db, root, 'native-research-manifest.json', manifest)
            report = ['# 原生 Claude 投研报告（证据受限）', '', manifest['notice'], '']
            for item in entries:
                report.extend(['## ' + item['role'], 'Child Run: ' + item['child_run_id'],
                               'Source IDs: ' + (', '.join(item['source_ids']) or '未评估'), ''])
            self.publish(db, root, 'native-research-report.md', '\n'.join(report), 'text/markdown')
            self.store.event(db, root, 'research.native.aggregated', {'coverage': manifest['coverage'],
                                                                       'source_count': len(source_entries), 'child_count': len(entries)})
            self.finish(db, root, 'succeeded', 'COMPLETED' if manifest['coverage'] == 'complete' else 'COMPLETED_WITH_WARNINGS')

    def recover(self):
        for root in self.store.listing('runs'):
            if root['selected_engine'] != ENGINE or root.get('parent_run_id'):
                continue
            children = self.children(root['id'])
            if root['status'] == 'running' or any(child['status'] == 'running' for child in children):
                self.fail_tree(root['id'], 'SERVER_RESTARTED')
