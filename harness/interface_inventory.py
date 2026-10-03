"""Generate an exhaustive registered-route inventory; never starts the app lifespan."""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path

from starlette.routing import Mount

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'specs/testing'


def features():
    return json.loads((DIRECTORY / 'features.json').read_text())['features']


def feature_for(path):
    matches = [(len(prefix), row['id']) for row in features() for prefix in row['prefixes']
               if path.startswith(prefix)]
    if not matches:
        raise ValueError(f'Unclassified route: {path}')
    # '/' is only a page fallback, never a catch-all for new API groups.
    length, ident = max(matches)
    if path.startswith('/api/') and length == 1:
        raise ValueError(f'Unclassified API: {path}')
    return ident


def build_inventory():
    from backend.app import create_app
    app = create_app(run_worker=False)
    rows = []
    for route in app.routes:
        mount = isinstance(route, Mount)
        path = route.path + '/{path:path}' if mount else route.path
        endpoint = getattr(route, 'endpoint', None)
        filename = inspect.getsourcefile(endpoint) if inspect.isfunction(endpoint) else None
        # A venv installed inside the repo is still framework code, not a
        # project source location. Do not freeze Python/site-packages paths.
        local = filename and Path(filename).resolve().is_relative_to(ROOT / 'backend')
        location = str(Path(filename).relative_to(ROOT)) + ':' + str(inspect.getsourcelines(endpoint)[1]) if local else 'framework'
        if mount:
            location = 'frontend/'
        for method in sorted(getattr(route, 'methods', None) or {'GET', 'HEAD'}):
            rows.append({'id': f'{method} {path}', 'method': method, 'path': path,
                         'kind': 'static_mount' if mount else 'api' if path.startswith('/api/') else 'page_or_schema',
                         'feature': feature_for(path), 'handler': getattr(endpoint, '__name__', route.name),
                         'source': location, 'in_openapi': bool(getattr(route, 'include_in_schema', False))})
    return {'version': 'interface-inventory@1', 'routes': sorted(rows, key=lambda row: row['id'])}


def render(inventory):
    lines = ['# HTTP / 页面 / 静态入口测试清单', '',
             '由 `python -m harness.interface_inventory --write` 生成；这里登记范围，不宣称验收完成。', '',
             f"总计 {len(inventory['routes'])} 个方法/路径组合；测试观测见 HA-0053 Evidence。", '',
             '| 方法与路径 | 功能 | 处理器 | 来源 | OpenAPI |', '|---|---|---|---|---|']
    for row in inventory['routes']:
        lines.append(f"| `{row['id']}` | {row['feature']} | `{row['handler']}` | `{row['source']}` | {'是' if row['in_openapi'] else '否'} |")
    lines.extend(['', '## 功能验收口径（含非 HTTP）', ''])
    for row in features():
        lines.extend([f"### {row['id']}：{row['title']}", '', row['boundary'], '',
                      '必须验证：' + '；'.join(row['checks']) + '。', '',
                      '规格：' + '、'.join(f'`{path}`' for path in row['specs']), '',
                      '测试入口：' + ('、'.join(f'`{path}`' for path in row['tests']) or '尚无运行时，不作通过声明'), ''])
    return '\n'.join(lines) + '\n'


def source_hashes():
    paths = [*ROOT.glob('backend/*.py'), *ROOT.glob('adapters/*.py'), *ROOT.glob('tests/test_*.py'),
             *ROOT.glob('specs/v1/*.json'), ROOT / 'specs/v1/openapi.yaml',
             ROOT / 'harness/pytest_interface_evidence.py', ROOT / 'harness/interface_inventory.py',
             DIRECTORY / 'features.json']
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths) if path.is_file()}


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    inventory = build_inventory()
    outputs = {DIRECTORY / 'interfaces.json': json.dumps(inventory, ensure_ascii=False, indent=2) + '\n',
               DIRECTORY / 'INTERFACES.md': render(inventory)}
    for path, expected in outputs.items():
        if args.write:
            path.write_text(expected)
        elif not path.is_file() or path.read_text() != expected:
            raise SystemExit(f'Stale interface inventory: {path.relative_to(ROOT)}; run --write')
    print(json.dumps({'route_methods': len(inventory['routes']), 'features': len(features()),
                      'mode': 'generated' if args.write else 'checked'}))


if __name__ == '__main__':
    main()
