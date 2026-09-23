"""Deterministic contract parse/classify/chunk/security preview.

This module implements the engineering half of lessons 16-18 without
starting Pi, calling a model, or sending document content to a network.
"""
from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator
from pypdf import PdfReader

from .analysis import Problem, digest
from .store import dumps


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'specs/v1/pi-contract-pipeline.schema.json').read_text())
HEADING = re.compile(r'(?=\n?\s*(?:第[一二三四五六七八九十百零]+章|第\d+条|\d+[.)、]\s))')

_TYPES = (
    ('技术服务', ('技术服务', '软件开发', '交付物', '源代码', 'software development', 'source code'), ('知识产权归属', '交付标准', '验收条款', '违约责任')),
    ('采购供货', ('采购', '供货', '买卖', '货款', 'procurement', 'supply'), ('付款条件', '交货期限', '质量标准', '退换货条款')),
    ('劳务用工', ('劳务', '用工', '劳动合同', '工资'), ('劳动关系', '保密义务', '竞业限制', '解除条件')),
    ('房屋租赁', ('租赁', '房屋', '租金', '房东'), ('租金支付', '押金退还', '维修责任', '提前解约')),
    ('股权投资', ('股权', '投资', '增资', '估值'), ('估值调整', '对赌条款', '股东权利', '退出机制')),
    ('保密协议', ('保密', '机密', '泄露'), ('保密范围', '保密期限', '违约责任', '例外情形')),
    ('合作协议', ('合作', '框架协议', '战略合作'), ('合作范围', '收益分配', '知识产权', '退出机制')),
)
_SENSITIVE = (
    ('身份证号', re.compile(r'\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]')),
    ('手机号', re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')),
    ('银行卡号', re.compile(r'(?<!\d)\d{16,19}(?!\d)')),
    ('邮箱', re.compile(r'(?i)[\w.-]+@[\w.-]+\.\w+')),
)


def _safe_heading(value: str) -> str:
    """Keep navigation useful while never returning sensitive literals."""
    for _name, pattern in _SENSITIVE:
        value = pattern.sub('[redacted]', value)
    return value[:160]


def _validate(kind: str, value: dict) -> None:
    errors = list(Draft202012Validator({'$ref': '#/$defs/' + kind, '$defs': SCHEMA['$defs']}).iter_errors(value))
    if errors:
        raise Problem('PI_PIPELINE_CONTRACT_INVALID', 'Pi 合同流水线结果不满足结构化契约。', 409)


def extract_pdf(raw: bytes) -> tuple[str, int]:
    if not raw.startswith(b'%PDF-'):
        raise Problem('PDF_RESOURCE_INVALID', '合同流水线只接受有效 PDF。', 422)
    try:
        reader = PdfReader(BytesIO(raw))
        text = '\n'.join((page.extract_text() or '') for page in reader.pages)
        page_count = len(reader.pages)
    except Exception as exc:
        raise Problem('PDF_PARSE_FAILED', 'PDF 文本解析失败。', 422) from exc
    text = re.sub(r'[ \t]+', ' ', text).replace('\r', '')
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    if not text:
        raise Problem('PDF_TEXT_EMPTY', 'PDF 没有可提取的文本，不能进入无模型预览。', 422)
    return text, page_count


def classify(text: str) -> dict:
    scores = [(sum(text.count(keyword) for keyword in keywords), name, focus) for name, keywords, focus in _TYPES]
    score, contract_type, focus = max(scores, key=lambda item: item[0])
    return {'contract_type': contract_type if score else '其他', 'focus_areas': list(focus if score else ('权利义务平衡', '违约责任', '争议解决', '合同期限')), 'method': 'deterministic_keyword_rules@1'}


def chunk(text: str, max_chars: int = 6000) -> list[dict]:
    parts = [part.strip() for part in HEADING.split(text) if part.strip()]
    chunks: list[str] = []
    current = ''
    for part in parts:
        if current and len(current) + len(part) + 1 > max_chars:
            chunks.append(current.strip())
            current = ''
        if len(part) > max_chars:
            for start in range(0, len(part), max_chars):
                piece = part[start:start + max_chars]
                if piece:
                    if current:
                        chunks.append(current.strip())
                        current = ''
                    chunks.append(piece)
        else:
            current = (current + '\n' + part).strip()
    if current:
        chunks.append(current)
    return [{'index': i, 'heading': (_safe_heading(item.splitlines()[0]) if item.splitlines() else ''), 'char_count': len(item), 'text_sha256': digest(item.encode())} for i, item in enumerate(chunks)]


def security_preview(text: str) -> dict:
    hits = [{'kind': name, 'count': len(pattern.findall(text))} for name, pattern in _SENSITIVE if pattern.search(text)]
    return {'status': 'needs_human' if hits else 'clear', 'hits': hits, 'external_calls': 0, 'model_calls': 0}


def build_preview(resource: dict, raw: bytes, chunk_max_chars: int = 6000) -> dict:
    if resource.get('data_class') != 'Public' or not resource.get('name', '').lower().endswith('.pdf'):
        raise Problem('PDF_RESOURCE_INVALID', '合同流水线只接受已登记 Public PDF。', 422)
    if not isinstance(chunk_max_chars, int) or not 1000 <= chunk_max_chars <= 16000:
        raise Problem('VALIDATION_ERROR', 'chunk_max_chars 必须在 1000–16000 之间。', 422)
    text, page_count = extract_pdf(raw)
    security = security_preview(text)
    result = {
        'schema_version': 'pi-contract-pipeline-preview@1', 'resource_id': resource['id'],
        'source_sha256': resource['sha256'], 'format': 'pdf', 'page_count': page_count,
        'char_count': len(text), 'classification': classify(text), 'chunks': chunk(text, chunk_max_chars),
        'security': security, 'status': 'needs_human' if security['status'] == 'needs_human' else 'ready_for_skill',
    }
    _validate('preview', result)
    return json.loads(dumps(result))


class PiContractPipeline:
    """Service facade for the offline Pi lessons 16-18 vertical slice."""

    def __init__(self, service):
        self.service = service
        self.store = service.store

    def preview(self, body: dict, key: str | None):
        if not isinstance(body, dict):
            raise Problem('VALIDATION_ERROR', '请求体必须是 JSON 对象。', 422)
        request = {name: body[name] for name in ('resource_id', 'chunk_max_chars') if name in body}
        _validate('request', request)
        resource = self.store.get('resources', request['resource_id'])

        def create(_db):
            with self.store.lock:
                raw = self.store.db.execute('SELECT raw FROM resources WHERE id=?', (resource['id'],)).fetchone()[0]
            return build_preview(resource, raw, request.get('chunk_max_chars', 6000))

        return self.service.idempotent('pi-contract-pipeline:preview', key, request, create)


__all__ = ['PiContractPipeline', 'build_preview', 'classify', 'chunk', 'extract_pdf', 'security_preview']
