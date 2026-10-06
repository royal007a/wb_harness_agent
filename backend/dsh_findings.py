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
_NUMERAL_CHARS = '0-9０-９,，.．零〇一二两三四五六七八九十百千万'
# A numeral token is the *whole* run of numeral characters before a unit; the
# look-behind forbids starting mid-token, so "3,030天" is never read as "030天".
_TOKEN_UNIT = re.compile(r'(?<![' + _NUMERAL_CHARS + r'])([' + _NUMERAL_CHARS + r']+)\s*' + _UNIT)
_CN_DIGITS = {'零': 0, '〇': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
_CN_SMALL = {'十': 10, '百': 100, '千': 1000}
_UNIT_CLASS = {'个工作日': 'workday', '工作日': 'workday', '自然日': 'day', '日': 'day', '天': 'day',
               '个月': 'month', '月': 'month', '年': 'year', '%': 'percent', '％': 'percent',
               '万元': 'wan_yuan', '元': 'yuan'}


class Unparseable(ValueError):
    pass


def _norm(text):
    return re.sub(r'\s+', '', text or '')


def _cn_to_int(text):
    """Chinese numerals up to 万 with 十/百/千 positions; anything else is unparseable."""
    if not text or any(c not in _CN_DIGITS and c not in _CN_SMALL and c != '万' for c in text):
        raise Unparseable(text)
    if text.count('万') > 1:
        raise Unparseable(text)
    if '万' in text:
        high, low = text.split('万')
        return _cn_to_int(high) * 10000 + (_cn_to_int(low) if low else 0)
    total, current, last_unit = 0, None, 10000
    for char in text:
        if char in _CN_DIGITS:
            if current is not None and current != 0:
                raise Unparseable(text)  # two digits in a row, e.g. "三三"
            current = _CN_DIGITS[char]
        else:
            unit = _CN_SMALL[char]
            if unit >= last_unit:
                raise Unparseable(text)
            total += (1 if current is None else current) * unit
            current, last_unit = None, unit
    return total + (current or 0)


def _parse_token(token):
    ascii_token = token.translate(str.maketrans('０１２３４５６７８９．，', '0123456789.,'))
    if re.fullmatch(r'[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?', ascii_token):
        return float(ascii_token.replace(',', ''))
    if re.fullmatch(r'[零〇一二两三四五六七八九十百千万]+', token):
        return float(_cn_to_int(token))
    raise Unparseable(token)  # mixed scripts, stray commas, "3千", etc.


def values(text, *, strict=False):
    """(number, unit-class) pairs from whole numeral tokens.

    strict=True raises Unparseable for a numeral the parser cannot read exactly,
    so claims are never "verified" on a truncated or guessed value.
    """
    found = set()
    for token, unit in _TOKEN_UNIT.findall(text or ''):
        if unit == '元' and token.endswith('万') and len(token) > 1:
            token, unit = token[:-1], '万元'
        try:
            found.add((_parse_token(token), _UNIT_CLASS[unit]))
        except Unparseable:
            if strict:
                raise
    return found


def parties(text):
    return {party for party in PARTIES if party in (text or '')}


def _bound_parties(text):
    """value -> parties named closest before each occurrence of that value (same quote)."""
    bound = {}
    for match in _TOKEN_UNIT.finditer(text or ''):
        token, unit = match.group(1), match.group(2)
        if unit == '元' and token.endswith('万') and len(token) > 1:
            token, unit = token[:-1], '万元'
        try:
            value = (_parse_token(token), _UNIT_CLASS[unit])
        except Unparseable:
            continue
        before = text[:match.start()]
        positions = {party: before.rfind(party) for party in PARTIES if party in before}
        if positions:
            bound.setdefault(value, set()).add(max(positions, key=positions.get))
    return bound


def unbound_party_values(claim, quotes):
    """HA-0111: for a single-party claim, values whose nearest preceding party in every
    quote is a different party (e.g. 甲方30日支付、乙方60日开票 → "乙方30日内支付")."""
    named = parties(claim)
    if len(named) != 1:
        return False
    (party,) = named
    try:
        claimed = values(claim, strict=True)
    except Unparseable:
        return False
    bound = {}
    for quote in quotes:
        for value, owners in _bound_parties(quote['text']).items():
            bound.setdefault(value, set()).update(owners)
    return any(value in bound and party not in bound[value] for value in claimed)


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


# Deterministic, conservative markers of text addressed to the model rather than to the
# contract parties (jikesummary 零信任/护栏三明治: rules, not an LLM judge).
INSTRUCTION_MARKERS = re.compile(
    r'忽略(?:以上|上述|之前|前面|先前|所有)[^。\n]{0,6}(?:指令|指示|提示|要求|规则)'
    r'|系统提示\s*[:：]|(?:请|你)(?:必须|应当|应该)?(?:直接)?按(?:此|本条|这里)(?:提交|输出|回答)'
    r'|ignore\s+(?:all\s+|any\s+)?(?:previous|prior|above)\s+(?:instructions|prompts)'
    r'|(?:^|\n)\s*(?:system|assistant)\s*[:：]', re.I)


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
        else:  # supported / conflicting share every mechanical claim check
            if not claim or not quotes:
                errors.append({'slot': slot, 'code': 'SUPPORTED_WITHOUT_EVIDENCE'})
                continue
            if status == 'conflicting' and len({q['clause_id'] for q in quotes}) < 2:
                errors.append({'slot': slot, 'code': 'CONFLICT_NEEDS_TWO_SOURCES'})
                continue
            quoted = '\n'.join(q['text'] for q in quotes)
            try:
                claimed = values(claim, strict=True)
            except Unparseable:
                errors.append({'slot': slot, 'code': 'CLAIM_VALUE_UNPARSEABLE'})
                continue
            if not claimed <= values(quoted):
                errors.append({'slot': slot, 'code': 'CLAIM_VALUE_NOT_IN_QUOTE'})
                continue
            if not parties(claim) <= parties(quoted):
                errors.append({'slot': slot, 'code': 'CLAIM_PARTY_NOT_IN_QUOTE'})
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
    # HA-0115: report both gaps (was elif); unread payment blocks are listed even when
    # an exception candidate is also unread. Exception candidates are payment blocks too,
    # so they are not repeated here.
    unread_payment_only = [k for k in unread_payment if k not in unread_exception]
    if unread_payment_only:
        platform_gaps.append({'code': 'PAYMENT_CLAUSES_UNREAD', 'clause_ids': unread_payment_only})
    # Every read exception candidate must be placed in the exception or conflict slot;
    # reporting one of two candidates does not cover the other.
    reported = {q['clause_id'] for slot in ('exception', 'conflict') for q in findings[slot]['quotes']}
    read_unreported = [k for k in found['exception'] if k in seen and k not in reported]
    if read_unreported:
        platform_gaps.append({'code': 'EXCEPTION_CANDIDATE_NOT_REPORTED', 'clause_ids': read_unreported})
    # Zero-trust content check (HA-0096): a literal quote can hide the instruction it
    # was lifted from. Flag (do not block) supported slots whose source block carries
    # deterministic instruction markers, so the published result says so.
    unbound = [slot for slot, f in findings.items() if f['status'] != 'unknown'
               and unbound_party_values(f['claim'], f['quotes'])]
    if unbound:
        # Heuristic, so a flag for human review rather than a rejection (commas and
        # subjects in earlier sentences make proximity binding unreliable to enforce).
        platform_gaps.append({'code': 'CLAIM_PARTY_VALUE_UNBOUND',
                              'clause_ids': sorted({q['clause_id'] for s in unbound for q in findings[s]['quotes']},
                                                   key=lambda k: int(k.split('-')[1]))})
    flagged = sorted({q['clause_id'] for f in findings.values() if f['status'] != 'unknown'
                      for q in f['quotes'] if INSTRUCTION_MARKERS.search(clauses[q['clause_id']])},
                     key=lambda k: int(k.split('-')[1]))
    if flagged:
        platform_gaps.append({'code': 'QUOTE_SOURCE_HAS_INSTRUCTION_MARKERS', 'clause_ids': flagged})
    statuses = {f['status'] for f in findings.values()}
    if 'conflicting' in statuses:
        business = 'conflicting'
    elif platform_gaps or 'unknown' in statuses or gaps:
        business = 'partial'
    else:
        business = 'mechanically_checked'
    return {'errors': [], 'findings': findings, 'model_gaps': list(gaps), 'platform_gaps': platform_gaps,
            'candidates': found, 'business_status': business}


_SLOT_NAMES = {'term': '付款期限', 'trigger': '触发条件', 'exception': '例外', 'conflict': '冲突'}
_STATUS_NAMES = {'supported': '有证据', 'unknown': '未知（无可核对证据）', 'conflicting': '冲突'}
_BUSINESS_NAMES = {'mechanically_checked': '机械校验通过', 'partial': '部分结果（有未知项或缺口）',
                   'conflicting': '存在冲突'}
_GAP_NAMES = {'EXCEPTION_CANDIDATES_UNREAD': '有付款例外候选证据块未读取',
              'PAYMENT_CLAUSES_UNREAD': '有付款相关证据块未读取',
              'EXCEPTION_CANDIDATE_NOT_REPORTED': '读到的例外候选未在例外/冲突中报告',
              'QUOTE_SOURCE_HAS_INSTRUCTION_MARKERS': '引文所在证据块含疑似注入指令，须人工核对原文',
              'CLAIM_PARTY_VALUE_UNBOUND': '结论中的主体与数值在引文中疑似不对应，须人工核对'}


def render_text(record):
    """The only published prose for payment_terms: built from the verified record.

    The model's free-form final answer is never published in this template, so it
    cannot reintroduce a value that differs from the checked findings.
    """
    lines = ['付款条件核对（平台根据通过机械校验的结构化结果生成）',
             f'结论状态：{_BUSINESS_NAMES[record["business_status"]]}，需人工复核', '']
    for slot in SLOTS:
        item = record['findings'][slot]
        lines.append(f'{_SLOT_NAMES[slot]}：{_STATUS_NAMES[item["status"]]}' + (f' — {item["claim"]}' if item['claim'] else ''))
        for quote in item['quotes']:
            lines.append(f'  · {quote["clause_id"]}：「{quote["text"]}」')
    if record['platform_gaps'] or record['model_gaps']:
        lines += ['', '缺口：']
        lines += [f'  · 平台：{_GAP_NAMES[g["code"]]}（{"、".join(g["clause_ids"])}）' for g in record['platform_gaps']]
        lines += [f'  · 模型自述：{g}' for g in record['model_gaps']]
    lines += ['', '校验范围：引文逐字来自本轮读过的证据块；结论中的数值、单位、甲乙方出现在引文中；例外候选是否读到并报告。',
              '未校验：结论在语义上是否被引文支持（例如否定词）、法律效力。']
    return '\n'.join(lines) + '\n'
