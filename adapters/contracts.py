"""Small synchronous adapter contract owned by the platform, not an SDK."""
from dataclasses import dataclass
from typing import Callable, Protocol

from backend.analysis import Problem


@dataclass(frozen=True)
class AdapterRequest:
    task: dict
    run: dict
    resource: dict
    input_bytes: bytes


@dataclass(frozen=True)
class AdapterResult:
    metrics: dict
    usage: dict


Emit = Callable[[str, dict], None]
Check = Callable[[], None]


class Adapter(Protocol):
    def describe(self) -> dict: ...
    def start_run(self, request: AdapterRequest, emit: Emit, check: Check) -> AdapterResult: ...
    def cancel_run(self, run_id: str) -> None: ...
    def cleanup(self, run_id: str) -> None: ...
    def restore_run(self, request: AdapterRequest, checkpoint: dict): ...


def validate_event(kind, data):
    # Only this event is emitted by the fixed tool adapter. SDK events are mapped
    # through a separate audited bridge, never forwarded unchecked.
    if kind != 'tool.call.completed' or data != {'tool': 'resource.inspect', 'implementation': 'deterministic'}:
        raise Problem('ADAPTER_PROTOCOL_ERROR', '适配器返回未授权事件。')


def validate_result(result):
    if not isinstance(result, AdapterResult) or result.usage != {'model_calls': 0, 'cost_minor': 0}:
        raise Problem('ADAPTER_PROTOCOL_ERROR', '固定分析器结果或用量协议不匹配。')
    if not isinstance(result.metrics, dict) or not isinstance(result.metrics.get('columns'), list):
        raise Problem('ADAPTER_PROTOCOL_ERROR', '适配器未返回结构化指标。')
