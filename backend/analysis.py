"""Bounded deterministic CSV tools. Never evaluates uploaded content or objectives."""
import csv
import hashlib
import html
import io
import json
import platform
from pathlib import Path
from decimal import Decimal, InvalidOperation

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 20000
MAX_COLUMNS = 100


class Problem(Exception):
    def __init__(self, code, message, status=400):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


ANALYSIS_CODE_SHA256 = digest(Path(__file__).read_bytes())


def parse_csv(raw):
    if not raw or len(raw) > MAX_BYTES:
        raise Problem('INVALID_RESOURCE', 'CSV 必须为 1 字节到 2 MiB。', 413)
    text = None
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            pass
    if text is None or '\x00' in text:
        raise Problem('INVALID_RESOURCE', '仅支持 UTF-8 或 GB18030 文本 CSV。')
    try:
        reader = csv.reader(io.StringIO(text, newline=''), strict=True)
        headers = next(reader)
        headers = [h.strip() for h in headers]
        if not headers or len(headers) > MAX_COLUMNS or any(not h or len(h) > 120 for h in headers) or len(set(headers)) != len(headers):
            raise Problem('INVALID_RESOURCE', '表头必须非空且唯一，最多 100 列，每个名称最多 120 字。')
        rows = []
        for row in reader:
            if not row:
                continue
            if len(row) != len(headers):
                raise Problem('INVALID_RESOURCE', f'第 {reader.line_num} 行列数不一致。')
            rows.append(row)
            if len(rows) > MAX_ROWS:
                raise Problem('INVALID_RESOURCE', '最多支持 20,000 行。')
        if not rows:
            raise Problem('INVALID_RESOURCE', 'CSV 至少需要一行数据。')
    except (csv.Error, StopIteration):
        raise Problem('INVALID_RESOURCE', 'CSV 格式无效。') from None
    return headers, rows, encoding


def number(value):
    try:
        n = Decimal(value.strip())
        return n if n.is_finite() and abs(n) <= Decimal('1e100') else None
    except InvalidOperation:
        return None


def analyze(raw, check=lambda: None):
    headers, rows, encoding = parse_csv(raw)
    columns = []
    for index, name in enumerate(headers):
        check()
        values = [row[index].strip() for row in rows]
        present = [v for v in values if v]
        nums = [number(v) for v in present]
        numeric = bool(present) and all(n is not None for n in nums)
        column = {'name': name, 'type': 'number' if numeric else 'text',
                  'missing': len(values) - len(present), 'distinct': len(set(present))}
        if numeric:
            total = sum(nums, Decimal(0))
            column.update(min=float(min(nums)), max=float(max(nums)), sum=float(total), mean=float(total / len(nums)))
        columns.append(column)
    return {'row_count': len(rows), 'column_count': len(headers), 'encoding': encoding,
            'missing_cells': sum(c['missing'] for c in columns), 'columns': columns,
            'preview': rows[:8]}


def markdown_text(value):
    return html.escape(str(value)).replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ')


def artifacts(resource, result, objective, run_id):
    lines = ['# 数据概览报告', '', '执行器：固定统计工具（无模型调用）。目标仅记录，本版不解释自然语言分析指令。', '',
             '目标：' + markdown_text(objective), '', f"来源：{resource['id']} · SHA-256 {resource['sha256']}", '',
             f"行数：{result['row_count']}；列数：{result['column_count']}；缺失单元格：{result['missing_cells']}", '',
             '| 字段 | 类型 | 缺失 | 不同值 | 最小 | 最大 | 均值 | 合计 |', '|---|---|---:|---:|---:|---:|---:|---:|']
    for c in result['columns']:
        lines.append('| ' + ' | '.join(markdown_text(c.get(k, '—')) for k in ('name', 'type', 'missing', 'distinct', 'min', 'max', 'mean', 'sum')) + ' |')
    lines += ['', '说明：数值列要求全部非空单元格可解析为有限数字；空字符串计为缺失。混合类型列保持文本。',
              '图表表示各列完整率，最多展示前 20 列；不跨不同计量单位比较数值。']
    report = '\n'.join(lines).encode()
    cols = result['columns'][:20]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="{85 + len(cols)*34}" viewBox="0 0 800 {85 + len(cols)*34}">',
             '<rect width="100%" height="100%" fill="#fafbf9"/><g font-family="sans-serif" fill="#20352d">',
             '<text x="24" y="34" font-size="20">Column completeness / 字段完整率</text>']
    for i, col in enumerate(cols):
        pct = 100 * (1 - col['missing'] / result['row_count'])
        y = 64 + 34 * i
        parts += [f'<text x="24" y="{y+15}" font-size="12">{html.escape(col["name"][:22])}</text>',
                  f'<rect x="230" y="{y}" width="450" height="20" rx="4" fill="#e4eae5"/>',
                  f'<rect x="230" y="{y}" width="{pct*4.5:.2f}" height="20" rx="4" fill="#44745b"/>',
                  f'<text x="698" y="{y+15}" font-size="12">{pct:.1f}%</text>']
    chart = (''.join(parts) + '</g></svg>').encode()
    manifest = {'schema_version': 1, 'run_id': run_id, 'input_sha256': resource['sha256'],
                'resource_id': resource['id'], 'engine': 'engine_mock_analytics', 'engine_version': '1.0.0',
                'analysis_code_sha256': ANALYSIS_CODE_SHA256,
                'runtime': {'python': platform.python_version(), 'numeric_implementation': 'stdlib.Decimal', 'decimal_precision': 28},
                'metrics': result, 'usage': {'model_calls': 0, 'cost_minor': 0},
                'artifacts': [{'name': name, 'sha256': digest(body)} for name, body in [('report.md', report), ('completeness.svg', chart)]]}
    return [('report.md', 'text/markdown', report), ('completeness.svg', 'image/svg+xml', chart),
            ('analysis-manifest.json', 'application/json', json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2).encode())]
