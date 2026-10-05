"""Narrow non-streaming OpenAI tool protocol. No routing, credentials or retries here."""
import json
import re
import httpx
from .analysis import Problem
from .business_budget import ModelCallResult

MODEL = 'doubao-seed-2.1-lite'
BASE = 'https://ark.cn-beijing.volces.com/api/coding/v3'
TOOL_NAMES = {'search_document', 'read_clause'}


def invalid():
    return Problem('DSH_PROVIDER_INVALID', '模型响应不满足受控工具协议。', 502)


def provider_payload(request):
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
    if {t['name'] for t in tools} != TOOL_NAMES or len(tools) != 2:
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
        if not isinstance(text, str) or len(text.encode()) > 65536 or len(raw_calls) > 4:
            raise invalid()
        if choice['finish_reason'] != ('tool_calls' if raw_calls else 'stop'):
            raise invalid()
        if not text.strip() and not raw_calls:
            raise invalid()
        calls, ids = [], set()
        for call in raw_calls:
            ident, function = call['id'], call['function']
            if (call['type'] != 'function' or function['name'] not in TOOL_NAMES or
                not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', ident) or ident in ids):
                raise invalid()
            args = function['arguments']
            if not isinstance(args, str) or len(args) > 1024 or not isinstance(json.loads(args), dict):
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
    async with httpx.AsyncClient(timeout=45, follow_redirects=False, trust_env=False) as client:
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


async def send_probe(payload, output_limit):
    """Explicit synthetic provider; the DSH process/loop/tools remain real."""
    results = [m for m in payload['messages'] if m['role'] == 'tool']
    if not results:
        return parse_response({'choices': [{'finish_reason': 'tool_calls', 'message': {
            'content': None, 'tool_calls': [{'id': 'call_probe_1', 'type': 'function', 'function': {
                'name': 'read_clause', 'arguments': '{"clause_id":"clause-1"}'}}]}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 30, 'total_tokens': 130}})
    return parse_response({'choices': [{'finish_reason': 'stop', 'message': {
        'content': '【合成 Provider 联调，非真实模型分析】\nDSH 已调用 read_clause 并收到：\n' + results[-1]['content']}}],
        'usage': {'prompt_tokens': 200, 'completion_tokens': 100, 'total_tokens': 300}})
