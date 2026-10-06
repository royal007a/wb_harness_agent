"""Narrow non-streaming OpenAI tool protocol. No routing, credentials or retries here."""
import json
import re
import httpx
from .analysis import Problem
from .business_budget import ModelCallResult

MODEL = 'doubao-seed-2.1-lite'
BASE = 'https://ark.cn-beijing.volces.com/api/coding/v3'
TOOL_NAMES = {'search_document', 'read_clause'}
FINDINGS_TOOL = 'submit_findings'
ALL_TOOL_NAMES = TOOL_NAMES | {FINDINGS_TOOL}
# Real doubao issues many parallel calls per turn on long contracts (HA-0080/0081); the
# per-Run tool cap (dsh_runtime.MAX_TOOL_CALLS) still bounds the total.
MAX_TOOL_CALLS_PER_RESPONSE = 16
# Per-tool argument size: structured findings need more room than a query.
ARGUMENT_LIMITS = {'search_document': 1024, 'read_clause': 1024, FINDINGS_TOOL: 8192}


def tool_names_for(template):
    return TOOL_NAMES | {FINDINGS_TOOL} if template == 'payment_terms' else set(TOOL_NAMES)


def invalid():
    return Problem('DSH_PROVIDER_INVALID', '模型响应不满足受控工具协议。', 502)


def provider_payload(request, expected_tools=TOOL_NAMES):
    if not isinstance(request, dict) or request.get('model') != MODEL or request.get('purpose') != 'primary':
        raise invalid()
    messages = []
    for message in request['messages']:
        role = message['role']
        if role not in {'system', 'developer', 'user', 'assistant', 'tool'}:
            raise invalid()
        text, calls = [], []
        for block in message['content']:
            if block['type'] == 'text':
                text.append(block['text'])
            elif block['type'] == 'tool-call' and role == 'assistant':
                calls.append({'id': block['id'], 'type': 'function',
                    'function': {'name': block['name'], 'arguments': block['arguments']}})
            elif block['type'] == 'tool-update':
                # Full current declarations below are authoritative.
                continue
            else:
                raise invalid()
        value = {'role': 'system' if role == 'developer' else role, 'content': '\n'.join(text)}
        if calls:
            value['tool_calls'] = calls
        if role == 'tool':
            value['tool_call_id'] = message['toolCallId']
        messages.append(value)
    tools = request.get('tools', [])
    if {t['name'] for t in tools} != set(expected_tools) or len(tools) != len(expected_tools):
        raise Problem('DSH_TOOL_POLICY', 'DSH 工具集合与平台策略不一致。', 409)
    return {'model': MODEL, 'messages': messages,
            'tools': [{'type': 'function', 'function': t} for t in tools], 'stream': False}


def parse_response(value):
    try:
        if len(value['choices']) != 1:
            raise invalid()
        choice = value['choices'][0]
        message = choice['message']
        text = message.get('content') or ''
        raw_calls = message.get('tool_calls') or []
        if not isinstance(text, str) or len(text.encode()) > 65536 or len(raw_calls) > MAX_TOOL_CALLS_PER_RESPONSE:
            raise invalid()
        if choice['finish_reason'] != ('tool_calls' if raw_calls else 'stop'):
            raise invalid()
        if not text.strip() and not raw_calls:
            raise invalid()
        calls, ids = [], set()
        for call in raw_calls:
            ident, function = call['id'], call['function']
            if (call['type'] != 'function' or function['name'] not in ALL_TOOL_NAMES or
                not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', ident) or ident in ids):
                raise invalid()
            args = function['arguments']
            if (not isinstance(args, str) or len(args) > ARGUMENT_LIMITS[function['name']]
                    or not isinstance(json.loads(args), dict)):
                raise invalid()
            ids.add(ident)
            calls.append({'id': ident, 'name': function['name'], 'arguments': args})
        usage = value['usage']
        normalized = {'input_tokens': usage['prompt_tokens'], 'output_tokens': usage['completion_tokens'],
                      'total_tokens': usage['total_tokens']}
        return ModelCallResult({'text': text, 'tool_calls': calls, 'usage': {
            'inputTokens': normalized['input_tokens'], 'outputTokens': normalized['output_tokens'],
            'totalTokens': normalized['total_tokens']}}, normalized)
    except (KeyError, TypeError, ValueError):
        raise invalid() from None


async def send_real(payload, output_limit, credential):
    body = {**payload, 'max_tokens': min(output_limit, 2048)}
    # The platform's budgeted call enforces the effective deadline; this is only an upper bound.
    async with httpx.AsyncClient(timeout=120, follow_redirects=False, trust_env=False) as client:
        async with client.stream('POST', BASE + '/chat/completions', json=body,
            headers={'Authorization': 'Bearer ' + credential, 'Accept-Encoding': 'identity'}) as response:
            if response.status_code != 200:
                raise Problem(f'DSH_PROVIDER_HTTP_{response.status_code}', 'Provider 请求失败；没有自动重试。', 502)
            if 'content-encoding' in response.headers:
                raise invalid()
            raw = bytearray()
            async for part in response.aiter_raw():
                raw.extend(part)
                if len(raw) > 256 * 1024:
                    raise invalid()
    return parse_response(json.loads(raw))


def _probe_reply(content=None, calls=(), usage=(100, 30)):
    message = {'content': content}
    if calls:
        message['tool_calls'] = [{'id': f'call_probe_{i}', 'type': 'function', 'function': {
            'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}} for i, (name, args) in enumerate(calls)]
    return parse_response({'choices': [{'finish_reason': 'tool_calls' if calls else 'stop', 'message': message}],
        'usage': {'prompt_tokens': usage[0], 'completion_tokens': usage[1], 'total_tokens': sum(usage)}})


_PROBE_LABEL = '【合成 Provider 联调，非真实模型分析】'


def _probe_payment(payload, results):
    """Deterministic, label-blind synthetic flow for the payment_terms template.

    Proves the DSH loop, tools, verification and publication run end to end; the
    "findings" are literal sentences copied from what was read, not analysis.
    """
    from .dsh_findings import EXCEPTION_LEXICON, PAYMENT_LEXICON, values
    clauses, last = {}, None
    for raw in results:
        try:
            value = json.loads(raw['content'])
        except (TypeError, ValueError):
            continue
        last = value
        items = value if isinstance(value, list) else value.get('matches', [])
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and isinstance(item.get('clause_id'), str) and isinstance(item.get('text'), str):
                clauses[item['clause_id']] = item['text']
    if last is None:
        return _probe_reply(calls=[('search_document', {'query': '付款'})])
    if isinstance(last, dict) and last.get('next_offset') is not None:
        return _probe_reply(calls=[('search_document', {'query': '付款', 'offset': last['next_offset']})])
    if isinstance(last, dict) and last.get('accepted') is True:
        return _probe_reply(_PROBE_LABEL + '\n已提交结构化结果；平台将发布其校验后的版本。', usage=(200, 60))
    if isinstance(last, dict) and 'coverage_gap' in last:
        ids = [i for i in last['coverage_gap'].get('clause_ids', []) if isinstance(i, str)][:4]
        return _probe_reply(calls=[('read_clause', {'clause_id': i}) for i in ids])
    if isinstance(last, dict) and last.get('accepted') is False:
        return _probe_reply(_PROBE_LABEL + '\n结构化结果未通过平台校验。', usage=(200, 40))

    def sentences(ident):
        body = clauses[ident].split('\n', 1)[-1]
        return [part.strip() for part in body.split('。') if len(part.strip()) >= 2]
    unknown = {'status': 'unknown', 'claim': '', 'quotes': []}
    term, exception_quotes = unknown, []
    for ident in sorted(clauses, key=lambda k: int(k.split('-')[1])):
        for sentence in sentences(ident):
            if term is unknown and PAYMENT_LEXICON.search(sentence) and values(sentence):
                term = {'status': 'supported', 'claim': sentence[:300],
                        'quotes': [{'clause_id': ident, 'text': sentence[:300]}]}
            if EXCEPTION_LEXICON.search(sentence) and PAYMENT_LEXICON.search(sentence) and \
                    ident not in {q['clause_id'] for q in exception_quotes}:
                exception_quotes.append({'clause_id': ident, 'text': sentence[:300]})
    exception = unknown
    if exception_quotes:
        exception = {'status': 'supported', 'claim': exception_quotes[0]['text'], 'quotes': exception_quotes[:3]}
    findings = {'term': term, 'trigger': unknown, 'exception': exception, 'conflict': unknown,
                'gaps': ['合成联调：触发条件与冲突未分析']}
    return _probe_reply(calls=[('submit_findings', findings)])


async def send_probe(payload, output_limit):
    """Explicit synthetic provider; the DSH process/loop/tools remain real."""
    results = [m for m in payload['messages'] if m['role'] == 'tool']
    if any(t['function']['name'] == FINDINGS_TOOL for t in payload.get('tools', [])):
        return _probe_payment(payload, results)
    if not results:
        return parse_response({'choices': [{'finish_reason': 'tool_calls', 'message': {
            'content': None, 'tool_calls': [{'id': 'call_probe_1', 'type': 'function', 'function': {
                'name': 'read_clause', 'arguments': '{"clause_id":"clause-1"}'}}]}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 30, 'total_tokens': 130}})
    return parse_response({'choices': [{'finish_reason': 'stop', 'message': {
        'content': '【合成 Provider 联调，非真实模型分析】\nDSH 已调用 read_clause 并收到：\n' + results[-1]['content']}}],
        'usage': {'prompt_tokens': 200, 'completion_tokens': 100, 'total_tokens': 300}})
