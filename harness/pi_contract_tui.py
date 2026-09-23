"""Small, deterministic terminal renderer for Pi contract review events.

This mirrors the course's event-to-TUI boundary without importing pi-tui or
starting a runtime. It renders metadata only; contract正文 is never printed.
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap


def render_event(event: str, data: dict, width: int = 88) -> str:
    width = max(40, min(int(width), 200))
    if event == 'preview':
        classification = data.get('classification', {}).get('contract_type', '未知')
        chunks = data.get('chunks', [])
        security = data.get('security', {}).get('status', 'unknown')
        return '\n'.join([
            'Pi Contract Review · offline',
            f'类型：{classification}  分块：{len(chunks)}  敏感状态：{security}',
            '分块：' + ', '.join(f"chunk-{item.get('index')}" for item in chunks[:32]),
        ])
    if event == 'finding':
        refs = data.get('evidence_refs', [])
        return '\n'.join([
            f"候选风险：{data.get('risk_level', 'unknown')} · 状态：{data.get('status', 'unknown')}",
            f"方法：{data.get('method', 'unknown')} · Evidence：{len(refs)} 条",
            textwrap.fill(str(data.get('recommendation', '')), width=width),
        ])
    if event == 'done':
        return f"完成 · model_calls={data.get('model_calls', 0)} external_calls={data.get('external_calls', 0)}"
    return '忽略未知事件（fail-closed）'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Render metadata-only contract review events')
    parser.add_argument('--input', default='-', help='JSONL event input; default stdin')
    parser.add_argument('--width', type=int, default=88)
    args = parser.parse_args(argv)
    stream = sys.stdin if args.input == '-' else open(args.input, encoding='utf-8')
    try:
        for line in stream:
            if not line.strip():
                continue
            item = json.loads(line)
            print(render_event(item.get('event', ''), item.get('data', {}), args.width))
    finally:
        if stream is not sys.stdin:
            stream.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
