"""Small, fail-closed client for the offline Pi JSONL sidecar.

This module owns transport only. It does not write Product Run state, resolve
credentials, or decide whether a real Provider is admitted.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCRIPT = ROOT / 'pi-adapter/src/sidecar.mjs'
PROTOCOL = 'pi-adapter@1'


@dataclass(frozen=True)
class PiSidecarConfig:
    node_path: str = 'node'
    script_path: Path = DEFAULT_SCRIPT
    startup_timeout_seconds: float = 3.0


class PiSidecarClient:
    def __init__(self, config: PiSidecarConfig = PiSidecarConfig()):
        self.config = config
        self.process: subprocess.Popen[str] | None = None

    def __enter__(self) -> 'PiSidecarClient':
        self.start_process()
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()

    def start_process(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return
        if not self.config.script_path.is_file():
            raise RuntimeError('PI_SIDECAR_SCRIPT_MISSING')
        self.process = subprocess.Popen(
            [self.config.node_path, str(self.config.script_path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def close(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)
        self.process = None

    def _send(self, payload: dict[str, Any]) -> None:
        if self.process is None or self.process.poll() is not None or self.process.stdin is None:
            raise RuntimeError('PI_SIDECAR_NOT_RUNNING')
        self.process.stdin.write(json.dumps(payload, separators=(',', ':')) + '\n')
        self.process.stdin.flush()

    def _read(self) -> dict[str, Any]:
        if self.process is None or self.process.stdout is None:
            raise RuntimeError('PI_SIDECAR_NOT_RUNNING')
        line = self.process.stdout.readline()
        if not line:
            detail = self.process.stderr.read() if self.process.stderr else ''
            raise RuntimeError(f'PI_SIDECAR_EOF:{detail[:300]}')
        return json.loads(line)

    def health(self) -> dict[str, Any]:
        self.start_process()
        self._send({'protocol': PROTOCOL, 'op': 'health'})
        while True:
            response = self._read()
            if response.get('op') == 'health':
                return response
            if response.get('op') == 'error':
                raise RuntimeError(response.get('code', 'PI_SIDECAR_ERROR'))

    def start(self, *, run_id: str, resource_ref: str, max_turns: int = 4) -> dict[str, Any]:
        self.start_process()
        self._send({
            'protocol': PROTOCOL, 'op': 'start', 'request_id': f'start-{run_id}', 'run_id': run_id,
            'model': {'provider': 'faux', 'model_id': 'offline-contract-review'},
            'resource_ref': resource_ref, 'capabilities': ['evidence.locate'],
            'limits': {'max_turns': max_turns},
        })
        while True:
            response = self._read()
            if response.get('op') in {'started', 'error'}:
                if response.get('op') == 'error':
                    raise RuntimeError(response.get('code', 'PI_SIDECAR_ERROR'))
                return response

    def drain_until_done(self, run_id: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        while True:
            response = self._read()
            if response.get('run_id') != run_id:
                continue
            if response.get('op') == 'event':
                events.append(response)
                if response.get('platform_type') == 'run.result.proposed':
                    return events
            elif response.get('op') == 'error':
                raise RuntimeError(response.get('code', 'PI_SIDECAR_ERROR'))

    def stream(self, *, run_id: str, after_seq: int = 0) -> dict[str, Any]:
        self._send({'protocol': PROTOCOL, 'op': 'stream', 'request_id': f'stream-{run_id}',
                    'run_id': run_id, 'after_seq': after_seq})
        events: list[dict[str, Any]] = []
        while True:
            response = self._read()
            if response.get('op') == 'event':
                events.append(response)
            if response.get('op') in {'stream_end', 'error'}:
                if response.get('op') == 'error':
                    raise RuntimeError(response.get('code', 'PI_SIDECAR_ERROR'))
                return {'events': events, 'done': response.get('done', False),
                        'next_seq': response.get('next_seq', 0)}

    def cancel(self, *, run_id: str) -> dict[str, Any]:
        self._send({'protocol': PROTOCOL, 'op': 'cancel', 'request_id': f'cancel-{run_id}', 'run_id': run_id})
        while True:
            response = self._read()
            if response.get('op') in {'cancelled', 'error'}:
                if response.get('op') == 'error':
                    raise RuntimeError(response.get('code', 'PI_SIDECAR_ERROR'))
                return response
