"""Payment-terms findings: platform-side mechanical verification (HA-0079).

Pure functions. The model proposes findings through ``submit_findings``; the
platform checks what can be checked mechanically and reports what cannot.

Accepted findings mean: every quote is a literal slice of a clause read in this
Run, numbers/units and contract parties in each claim appear in its quotes, and
exception candidates the platform found were either read or reported as a gap.
They do NOT mean the claim is semantically supported or legally correct; that
remains human review.
"""
from __future__ import annotations

import re

SLOTS = ('term', 'trigger', 'exception', 'conflict')
STATUSES = ('supported', 'unknown', 'conflicting')
MAX_QUOTES = 3
MAX_CLAIM = 300
MAX_QUOTE = 300
MAX_GAPS = 8

# Words that commonly introduce a payment exception or suspension. Literal
# lexicon only: it cannot find every implicit exception, so an unmatched
# document is never reported as "fully covered" by this list.
EXCEPTION_LEXICON = re.compile(r'例外|除外|除非|暂停|争议|不适用|免除|延期|中止|扣留|另行')
PAYMENT_LEXICON = re.compile(r'付款|支付|结算|账期|货款|价款|合同款')
PARTIES = ('甲方', '乙方', '丙方')
_UNIT = r'(个工作日|工作日|自然日|个月|日|天|月|年|%|％|万元|元)'
_NUMBER_UNIT = re.compile(r'(\d+(?:\.\d+)?)\s*' + _UNIT)
_CN_DIGITS = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
_CN_NUMBER_UNIT = re.compile(r'([零一二两三四五六七八九十百]+)\s*' + _UNIT)
_UNIT_CLASS = {'个工作日': 'workday', '工作日': 'workday', '自然日': 'day', '日': 'day', '天': 'day',
               '个月': 'month', '月': 'month', '年': 'year', '%': 'percent', '％': 'percent',
               '万元': 'wan_yuan', '元': 'yuan'}


def _norm(text):
    return re.sub(r'\s+', '', text or '')


def _cn_to_int(text):
    if not text:
        return None
    if text == '十':
        return 10
    total, current = 0, 0
    for char in text:
        if char in _CN_DIGITS:
            current = _CN_DIGITS[char]
        elif char == '十':
            total += (current or 1) * 10
            current = 0
        elif char == '百':
            total += (current or 1) * 100
            current = 0
    return total + current


def values(text):
    """(number, unit-class) pairs, Arabic and simple Chinese numerals."""
    found = set()
    for number, unit in _NUMBER_UNIT.findall(text or ''):
        found.add((float(number), _UNIT_CLASS[unit]))
    for number, unit in _CN_NUMBER_UNIT.findall(text or ''):
        value = _cn_to_int(number)
        if value is not None:
            found.add((float(value), _UNIT_CLASS[unit]))
    return found


def parties(text):
    return {party for party in PARTIES if party in (text or '')}


def candidates(clauses):
    """Platform-computed clause IDs a payment review must not silently skip."""
    payment = sorted(k for k, t in clauses.items() if PAYMENT_LEXICON.search(t))
    exception = sorted(k for k, t in clauses.items() if EXCEPTION_LEXICON.search(t) and PAYMENT_LEXICON.search(t))
    return {'payment': payment, 'exception': exception}


def _check_quotes(slot, quotes, clauses, seen, errors):
    if not isinstance(quotes, list) or len(quotes) > MAX_QUOTES:
        errors.append({'slot': slot, 'code': 'QUOTES_INVALID'})
        return []
    good = []
    for quote in quotes:
        if not isinstance(quote, dict) or set(quote) != {'clause_id', 'text'} or \
                not isinstance(quote['clause_id'], str) or not isinstance(quote['text'], str):
            errors.append({'slot': slot, 'code': 'QUOTES_INVALID'})
            continue
        ident, text = quote['clause_id'], quote['text']
        if ident not in clauses or ident not in seen:
            # Covers made-up IDs and IDs from another Run/document: only clauses
            # this Run actually returned to the model are citable.
            errors.append({'slot': slot, 'code': 'QUOTE_CLAUSE_NOT_READ'})
            continue
        if not 2 <= len(_norm(text)) <= MAX_QUOTE or _norm(text) not in _norm(clauses[ident]):
            errors.append({'slot': slot, 'code': 'QUOTE_NOT_IN_SOURCE'})
            continue
        good.append({'clause_id': ident, 'text': text})
    return good


def verify(submission, clauses, seen):
    """Return {'errors': [...], 'findings': ..., 'gaps': [...], 'business_status': ...}.

    ``errors`` use a fixed code vocabulary only; they never echo model text.
    """
    errors = []
    if not isinstance(submission, dict) or set(submission) - set(SLOTS) - {'gaps'}:
        return {'errors': [{'slot': '*', 'code': 'SUBMISSION_INVALID'}]}
    findings = {}
    for slot in SLOTS:
        item = submission.get(slot)
        if not isinstance(item, dict) or set(item) != {'status', 'claim', 'quotes'} or \
                item['status'] not in STATUSES or not isinstance(item['claim'], str) or \
                len(item['claim']) > MAX_CLAIM:
            errors.append({'slot': slot, 'code': 'SLOT_MISSING_OR_INVALID'})
            continue
        status, claim = item['status'], item['claim'].strip()
        if not isinstance(item['quotes'], list):
            errors.append({'slot': slot, 'code': 'QUOTES_INVALID'})
            continue
        quotes = _check_quotes(slot, item['quotes'], clauses, seen, errors)
        if len(quotes) != len(item['quotes']):
            continue
        if status == 'unknown':
            if quotes:
                errors.append({'slot': slot, 'code': 'UNKNOWN_WITH_QUOTES'})
                continue
        elif status == 'supported':
            if not claim or not quotes:
                errors.append({'slot': slot, 'code': 'SUPPORTED_WITHOUT_EVIDENCE'})
                continue
            quoted = ''.join(q['text'] for q in quotes)
            if not values(claim) <= values(quoted):
                errors.append({'slot': slot, 'code': 'CLAIM_VALUE_NOT_IN_QUOTE'})
                continue
            if not parties(claim) <= parties(quoted):
                errors.append({'slot': slot, 'code': 'CLAIM_PARTY_NOT_IN_QUOTE'})
                continue
        else:  # conflicting
            if len({q['clause_id'] for q in quotes}) < 2:
                errors.append({'slot': slot, 'code': 'CONFLICT_NEEDS_TWO_SOURCES'})
                continue
        findings[slot] = {'status': status, 'claim': claim, 'quotes': quotes}
    gaps = submission.get('gaps', [])
    if not isinstance(gaps, list) or len(gaps) > MAX_GAPS or \
            any(not isinstance(g, str) or not 1 <= len(g) <= 200 for g in gaps):
        errors.append({'slot': 'gaps', 'code': 'GAPS_INVALID'})
    if errors:
        return {'errors': errors}
    found = candidates(clauses)
    platform_gaps = []
    unread_exception = [k for k in found['exception'] if k not in seen]
    unread_payment = [k for k in found['payment'] if k not in seen]
    if unread_exception:
        platform_gaps.append({'code': 'EXCEPTION_CANDIDATES_UNREAD', 'clause_ids': unread_exception})
    elif unread_payment:
        platform_gaps.append({'code': 'PAYMENT_CLAUSES_UNREAD', 'clause_ids': unread_payment})
    reported = {q['clause_id'] for q in findings['exception']['quotes']}
    read_unreported = [k for k in found['exception'] if k in seen and k not in reported]
    if read_unreported and findings['exception']['status'] == 'unknown':
        # The model read an exception-looking clause but reported no exception.
        platform_gaps.append({'code': 'EXCEPTION_CANDIDATE_NOT_REPORTED', 'clause_ids': read_unreported})
    statuses = {f['status'] for f in findings.values()}
    if 'conflicting' in statuses:
        business = 'conflicting'
    elif platform_gaps or 'unknown' in statuses or gaps:
        business = 'partial'
    else:
        business = 'mechanically_checked'
    return {'errors': [], 'findings': findings, 'model_gaps': list(gaps), 'platform_gaps': platform_gaps,
            'candidates': found, 'business_status': business}
