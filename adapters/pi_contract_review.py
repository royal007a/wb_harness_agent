"""Offline Pi contract-review adapter boundary.

This is deliberately a Product-Adapter-shaped seam, not a production runtime:
it accepts only a registered Public PDF, invokes the Faux-only Pi sidecar, and
returns a cited, human-gated finding.  No model, network, credential or host
path is reachable through this module.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from backend.analysis import Problem, digest
from .pi_sidecar import PiSidecarClient


@dataclass(frozen=True)
class PiContractReviewResult:
    finding: dict[str, Any]
    usage: dict[str, int]


class PiContractReviewAdapter:
    adapter_id = 'pi_contract_review_offline'
    adapter_version = '0.1.0'

    def describe(self) -> dict[str, Any]:
        return {
            'adapter_id': self.adapter_id,
            'adapter_version': self.adapter_version,
            'protocol_version': 'pi-adapter@1',
            'engine': 'engine_pi_contract_review_offline',
            'mode': 'faux_provider_only',
            'capabilities': {
                'actions.tool_call': True,
                'output.structured': True,
                'artifacts.files': False,
                'control.cancel': {'supported': False, 'reason': 'sidecar probe is bounded and synchronous'},
                'state.checkpoint': {'supported': False},
                'state.restore': {'supported': False},
                'external.model': False,
                'external.network': False,
            },
        }

    @staticmethod
    def _extract_finding(events: list[dict[str, Any]], resource_id: str) -> dict[str, Any]:
        terminal = next((item for item in reversed(events) if item.get('platform_type') == 'run.result.proposed'), None)
        if terminal is None:
            raise Problem('PI_RESULT_MISSING', 'Pi sidecar 未产生终止结果。', 409)
        messages = terminal.get('payload', {}).get('messages', [])
        text = ''
        for message in reversed(messages):
            if message.get('role') != 'assistant':
                continue
            for content in message.get('content', []):
                if content.get('type') == 'text' and content.get('text', '').startswith('{'):
                    text = content['text']
                    break
            if text:
                break
        try:
            finding = json.loads(text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise Problem('PI_RESULT_INVALID', 'Pi 结果不是合法结构化 JSON。', 409) from exc
        required = {'status', 'risk_level', 'evidence_refs', 'recommendation'}
        if set(finding) != required or finding['status'] != 'needs_human' or finding['risk_level'] != 'high':
            raise Problem('PI_RESULT_INVALID', '离线合同审查结果未满足固定风险输出契约。', 409)
        refs = finding['evidence_refs']
        if not isinstance(refs, list) or not refs or any(
            not isinstance(ref, str) or not ref.startswith(f'evidence://{resource_id}/') for ref in refs
        ):
            raise Problem('PI_EVIDENCE_INVALID', '合同审查结果缺少绑定到当前资源的 Evidence 引用。', 409)
        return {
            'schema_version': 'pi-contract-review@1',
            **finding,
            'source_resource_id': resource_id,
            'verification': 'sidecar_event_and_evidence_ref_checked',
            'gate': {'status': 'needs_human', 'reason': '高风险条款必须人工确认'},
        }

    def start_run(self, request, emit, check) -> PiContractReviewResult:
        if not request.resource.get('name', '').lower().endswith('.pdf') or not request.input_bytes.startswith(b'%PDF-'):
            raise Problem('PDF_RESOURCE_INVALID', 'Pi 合同审查探针只接受已登记 PDF。', 422)
        resource_id = request.resource['id']
        run_id = request.run['id']
        check()
        with PiSidecarClient() as client:
            health = client.health()
            if health.get('runtime_enabled') or health.get('external_calls') != 0:
                raise Problem('PI_RUNTIME_NOT_OFFLINE', 'Pi 探针运行时越过了离线门禁。', 409)
            client.start(run_id=run_id, resource_ref=resource_id)
            events = client.drain_until_done(run_id)
            for event in events:
                check()
                emit(event['platform_type'], event.get('payload', {}))
        finding = self._extract_finding(events, resource_id)
        return PiContractReviewResult(finding=finding, usage={'model_calls': 0, 'cost_minor': 0, 'network_calls': 0})

    def checkpoint_run(self, request, result):
        raise Problem('CHECKPOINT_UNSUPPORTED', '离线 Pi 合同审查探针不提供 Product Checkpoint。', 409)

    def restore_run(self, request, checkpoint):
        raise Problem('RESTORE_UNSUPPORTED', '离线 Pi 合同审查探针不提供 Product Restore。', 409)

    def cancel_run(self, run_id: str) -> None:
        # The sidecar itself has a cancel contract; this synchronous adapter
        # never exposes a live Product Run, so no cancellation is claimed here.
        return None

    def cleanup(self, run_id: str) -> None:
        return None


__all__ = ['PiContractReviewAdapter', 'PiContractReviewResult']
