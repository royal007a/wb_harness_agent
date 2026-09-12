"""Audited fixed functions, not an LLM, not a financial advisory engine."""
import json
from decimal import Decimal

from backend.analysis import Problem, digest

COMPANIES = {'demo_a': '演示公司 A', 'demo_b': '演示公司 B', 'demo_c': '演示公司 C'}
ROLES = {'financial': '财务指标', 'industry': '行业资料', 'risk': '风险资料覆盖'}


def fixture(company, role, scenario):
    number = list(COMPANIES).index(company) + 1
    base = {'synthetic': True, 'company': company, 'role': role, 'period': 'DEMO-PERIOD',
            'source': 'project-authored-synthetic-fixture-v1', 'unit': '演示单位'}
    if role == 'financial':
        base['data'] = {'revenue': str(number * 1000), 'profit': str(number * 100),
                        'assets': str(number * 2000), 'liabilities': str(number * 600)}
    elif role == 'industry':
        base['data'] = {'notes': ['模拟资料：需求变化观察', '模拟资料：原材料成本观察'], 'live_news': False}
    else:
        base['data'] = None if scenario == 'missing_risk' else {'coverage': ['financial_snapshot'],
                            'missing': ['regulatory_announcements', 'audit_opinion', 'litigation', 'live_market']}
    return json.dumps(base, sort_keys=True, ensure_ascii=False).encode()


def evaluate(raw, resource_id):
    source = json.loads(raw)
    if source['data'] is None:
        raise Problem('SOURCE_UNAVAILABLE', '演示风险资料缺失；不能推断为无风险。')
    role, data = source['role'], source['data']
    if role == 'financial':
        metrics = {'profit_margin': str(Decimal(data['profit']) / Decimal(data['revenue'])),
                   'liabilities_to_assets': str(Decimal(data['liabilities']) / Decimal(data['assets']))}
        summary = '基于模拟数据完成净利率和资产负债比例计算；不代表真实财报。'
    elif role == 'industry':
        metrics = {'provided_notes': len(data['notes']), 'live_news': False}
        summary = '整理了本地模拟行业资料；没有进行联网新闻搜索或热度评估。'
    else:
        metrics = {'risk_assessment': 'not_assessed', 'missing_sources': data['missing']}
        summary = '风险证据不完整，无法判断 ST、退市、诉讼等风险；不能解释为安全。'
    return {'synthetic': True, 'company': source['company'], 'role': role,
            'summary': summary, 'metrics': metrics,
            'evidence': [{'resource_id': resource_id, 'sha256': digest(raw), 'source': source['source']}]}


class ResearchDemoExecutor:
    version = '1.0.0'

    def run(self, context, check):
        check()
        if context['allowed_tools'] != ['resource.inspect']:
            raise Problem('FORBIDDEN', '演示执行器仅接受资源读取能力。')
        result = evaluate(context['input_bytes'], context['resource_id'])
        check()
        return result
