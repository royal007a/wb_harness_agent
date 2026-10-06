"""Tool-capable OpenAI-compatible stream adapter; no business state or retry policy."""
import json
import re

import httpx

from .provider_adapters import _sse_data, _unique_object, _invalid_constant
from .support_providers import fail


async def stream_completion(providers, provider_id, payload):
    providers.require_enabled()
    with providers.store.lock:
        row = providers._row(provider_id)
        doc = json.loads(row['doc'])
        if not doc['enabled'] or doc['base_url'] not in providers.allowed_bases:
            raise fail('SUPPORT_PROVIDER_DISABLED', 409)
        secret = providers.vault.decrypt(provider_id, row['ciphertext'])
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10), trust_env=False,
                                     follow_redirects=False, transport=providers.transport) as client:
            async with client.stream('POST', doc['base_url'] + '/chat/completions',
                    json={**payload, 'stream': True, 'stream_options': {'include_usage': True}},
                    headers={'Authorization': 'Bearer ' + secret, 'Accept': 'text/event-stream',
                             'Accept-Encoding': 'identity'}) as response:
                if response.status_code != 200:
                    raise fail('SUPPORT_PROVIDER_AUTH' if response.status_code in (401, 403) else 'SUPPORT_PROVIDER_HTTP', 502)
                if 'content-encoding' in response.headers or response.headers.get('content-type', '').split(';')[0] != 'text/event-stream':
                    raise fail('SUPPORT_PROVIDER_INVALID', 502)
                text, calls, finished, usage, completion_id = '', {}, None, None, None
                async for data in _sse_data(response):
                    if data == '[DONE]':
                        if finished is None or usage is None:
                            raise fail('SUPPORT_INCOMPLETE_STREAM', 502)
                        message = {'role': 'assistant', 'content': text or None}
                        if calls:
                            if sorted(calls) != list(range(len(calls))):
                                raise fail('SUPPORT_PROVIDER_INVALID', 502)
                            tool_calls = [calls[i] for i in sorted(calls)]
                            if len({c['id'] for c in tool_calls}) != len(tool_calls):
                                raise fail('SUPPORT_PROVIDER_INVALID', 502)
                            for call in tool_calls:
                                if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', call['id']) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', call['function']['name']):
                                    raise fail('SUPPORT_PROVIDER_INVALID', 502)
                            message['tool_calls'] = tool_calls
                        elif not text.strip():
                            raise fail('SUPPORT_EMPTY_RESPONSE', 502)
                        yield {'result': {'message': message, 'usage': usage}}
                        return
                    item = json.loads(data, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
                    if not isinstance(item, dict) or item.get('error') or not isinstance(item.get('id'), str):
                        raise fail('SUPPORT_PROVIDER_INVALID', 502)
                    if completion_id is not None and completion_id != item['id']:
                        raise fail('SUPPORT_PROVIDER_INVALID', 502)
                    completion_id = item['id']
                    if item.get('usage') is not None:
                        if usage is not None:
                            raise fail('SUPPORT_PROVIDER_INVALID', 502)
                        raw_usage = item['usage']
                        if not isinstance(raw_usage, dict) or any(type(raw_usage.get(k)) is not int or not 0 <= raw_usage[k] <= 20000000
                                for k in ('prompt_tokens', 'completion_tokens')):
                            raise fail('SUPPORT_USAGE_INVALID', 502)
                        usage = {'input_tokens': raw_usage['prompt_tokens'], 'output_tokens': raw_usage['completion_tokens']}
                        usage['total_tokens'] = usage['input_tokens'] + usage['output_tokens']
                    choices = item.get('choices')
                    if choices == [] and finished is not None and usage is not None:
                        continue
                    if finished is not None or not isinstance(choices, list) or len(choices) != 1:
                        raise fail('SUPPORT_PROVIDER_INVALID', 502)
                    choice = choices[0]
                    if not isinstance(choice, dict) or type(choice.get('index')) is not int or choice['index'] != 0:
                        raise fail('SUPPORT_PROVIDER_INVALID', 502)
                    delta = choice.get('delta')
                    if not isinstance(delta, dict) or delta.get('role') not in (None, 'assistant') or delta.get('refusal') or delta.get('function_call'):
                        raise fail('SUPPORT_PROVIDER_INVALID', 502)
                    content = delta.get('content')
                    if content is not None:
                        if not isinstance(content, str):
                            raise fail('SUPPORT_PROVIDER_INVALID', 502)
                        text += content
                        if len(text) > 65536:
                            raise fail('SUPPORT_PROVIDER_LIMIT', 502)
                        if content:
                            yield {'delta': content}
                    fragments = delta.get('tool_calls', [])
                    if not isinstance(fragments, list):
                        raise fail('SUPPORT_PROVIDER_INVALID', 502)
                    for fragment in fragments:
                        if not isinstance(fragment, dict) or type(fragment.get('index')) is not int or not 0 <= fragment['index'] < 4:
                            raise fail('SUPPORT_PROVIDER_INVALID', 502)
                        target = calls.setdefault(fragment['index'], {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
                        function = fragment.get('function', {})
                        if not isinstance(function, dict) or fragment.get('type') not in (None, 'function'):
                            raise fail('SUPPORT_PROVIDER_INVALID', 502)
                        for dest, key, value, limit in ((target, 'id', fragment.get('id'), 128),
                            (target['function'], 'name', function.get('name'), 80),
                            (target['function'], 'arguments', function.get('arguments'), 8192)):
                            if value is not None:
                                if not isinstance(value, str) or len(dest[key]) + len(value) > limit:
                                    raise fail('SUPPORT_PROVIDER_INVALID', 502)
                                dest[key] += value
                    reason = choice.get('finish_reason')
                    if reason is not None:
                        if reason not in ('stop', 'tool_calls') or (reason == 'tool_calls') != bool(calls):
                            raise fail('SUPPORT_OUTPUT_NOT_COMPLETE', 502)
                        finished = reason
                raise fail('SUPPORT_INCOMPLETE_STREAM', 502)
    except (httpx.HTTPError, TimeoutError):
        raise fail('SUPPORT_PROVIDER_UNAVAILABLE', 502) from None
    except (ValueError, UnicodeError, RecursionError):
        raise fail('SUPPORT_PROVIDER_INVALID', 502) from None
