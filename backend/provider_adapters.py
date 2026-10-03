"""Protocol-only model-provider adapters for the isolated local chat runtime.

This module deliberately has no configuration storage and no policy decisions.  A
caller must pass a resolved credential and explicitly enable the runtime before
an adapter can make a network request.
"""
from __future__ import annotations

import asyncio
import codecs
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from .analysis import Problem


MAX_STREAM_BYTES = 2 * 1024 * 1024
MAX_FRAME_CHARS = 256 * 1024
_LINE_BREAK = re.compile(r'[\r\n]')


def invalid_response():
    return Problem('MODEL_PROVIDER_INVALID_RESPONSE', '模型 Provider 返回了不符合协议的数据。', 502)


def response_limit():
    return Problem('MODEL_PROVIDER_RESPONSE_LIMIT', '模型 Provider 流超过协议大小上限。', 502)


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate JSON key')
        value[key] = item
    return value


def _invalid_constant(_):
    raise ValueError('non-JSON numeric constant')


class _SSEFrames:
    """Incremental, bounded UTF-8 SSE framing, including split CRLF and data lines."""

    def __init__(self):
        self.decoder = codecs.getincrementaldecoder('utf-8-sig')()
        self.buffer = ''
        self.data = []
        self.frame_chars = 0

    def feed(self, raw, *, final=False):
        try:
            self.buffer += self.decoder.decode(raw, final=final)
        except UnicodeDecodeError:
            raise invalid_response() from None
        cursor = 0
        while match := _LINE_BREAK.search(self.buffer, cursor):
            end = match.start()
            # A CR at the chunk boundary might be half of a CRLF.
            if self.buffer[end] == '\r' and end + 1 == len(self.buffer) and not final:
                break
            width = 2 if self.buffer[end:end + 2] == '\r\n' else 1
            line = self.buffer[cursor:end]
            cursor = end + width
            self.frame_chars += len(line) + width
            if self.frame_chars > MAX_FRAME_CHARS:
                raise response_limit()
            if not line:
                if self.data:
                    yield '\n'.join(self.data)
                self.data, self.frame_chars = [], 0
            elif not line.startswith(':'):
                field, _, value = line.partition(':')
                if field == 'data':
                    self.data.append(value[1:] if value.startswith(' ') else value)
        self.buffer = self.buffer[cursor:]
        if self.frame_chars + len(self.buffer) > MAX_FRAME_CHARS:
            raise response_limit()
        # EOF never dispatches an unterminated frame. Adapter will report incomplete.


async def _sse_data(response):
    frames, received = _SSEFrames(), 0
    async for raw in response.aiter_raw():
        received += len(raw)
        if received > MAX_STREAM_BYTES:
            raise response_limit()
        # Do not make a large comment/blank-line batch monopolize the event loop.
        for offset in range(0, len(raw), 4096):
            for data in frames.feed(raw[offset:offset + 4096]):
                yield data
            await asyncio.sleep(0)
    for data in frames.feed(b'', final=True):
        yield data


@dataclass(frozen=True)
class ProviderRequest:
    base_url: str
    credential: str
    model_id: str
    system_prompt: str
    messages: tuple[dict[str, str], ...]
    temperature: float
    max_output_tokens: int


class ProviderAdapter:
    """Translate one provider wire protocol; never owns Agent behavior."""

    adapter_status = "not_implemented"

    async def stream(self, request: ProviderRequest) -> AsyncIterator[str]:
        """Normal completion certifies protocol success, not mere network exhaustion."""
        raise Problem('PROVIDER_ADAPTER_NOT_IMPLEMENTED', '该 Provider 协议尚未实现，系统不会自动切换模型。', 409)
        yield ''  # pragma: no cover - makes this an async generator for type checkers


class OpenAIChatCompletionsAdapter(ProviderAdapter):
    """A narrowly scoped OpenAI-compatible `/chat/completions` SSE translator."""

    adapter_status = "supported"

    async def stream(self, request: ProviderRequest) -> AsyncIterator[str]:
        payload = {
            'model': request.model_id,
            'stream': True,
            'temperature': request.temperature,
            'max_tokens': request.max_output_tokens,
            'messages': [{'role': 'system', 'content': request.system_prompt}, *request.messages],
        }
        endpoint = request.base_url.rstrip('/') + '/chat/completions'
        headers = {'Authorization': 'Bearer ' + request.credential, 'Accept': 'text/event-stream',
                   'Accept-Encoding': 'identity'}
        try:
            timeout = httpx.Timeout(connect=10.0, read=90.0, write=20.0, pool=10.0)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
                async with client.stream('POST', endpoint, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    # Reject before body iteration: decoded-size limits alone cannot
                    # prevent a compressed network block expanding before the check.
                    if 'content-encoding' in response.headers:
                        raise invalid_response()
                    if response.headers.get('content-type', '').split(';')[0].strip().lower() != 'text/event-stream':
                        raise invalid_response()
                    stopped, usage_seen, completion_id = False, False, None
                    async for data in _sse_data(response):
                        if data == '[DONE]':
                            if not stopped:
                                raise Problem('MODEL_PROVIDER_INCOMPLETE_STREAM', '模型流缺少完整成功终止。', 502)
                            return
                        try:
                            item = json.loads(data, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
                        except (ValueError, RecursionError):
                            raise invalid_response() from None
                        if not isinstance(item, dict):
                            raise invalid_response()
                        if item.get('error') is not None:
                            raise Problem('MODEL_PROVIDER_REJECTED', '模型 Provider 返回错误。', 502)
                        identifier = item.get('id')
                        if (not isinstance(identifier, str) or not identifier or len(identifier) > 256
                                or item.get('object') != 'chat.completion.chunk'
                                or (completion_id is not None and identifier != completion_id)):
                            raise invalid_response()
                        completion_id = identifier
                        choices = item.get('choices')
                        if choices == [] and isinstance(item.get('usage'), dict) and stopped and not usage_seen:
                            usage_seen = True
                            continue
                        if stopped or not isinstance(choices, list) or len(choices) != 1:
                            raise invalid_response()
                        choice = choices[0]
                        if (not isinstance(choice, dict) or type(choice.get('index')) is not int
                                or choice['index'] != 0 or not isinstance(choice.get('delta'), dict)):
                            raise invalid_response()
                        delta = choice['delta']
                        content, reason = delta.get('content'), choice.get('finish_reason')
                        if (content is not None and not isinstance(content, str)) or delta.get('role') not in (None, 'assistant'):
                            raise invalid_response()
                        if ((delta.get('refusal') is not None and not isinstance(delta['refusal'], str))
                                or (delta.get('tool_calls') is not None and not isinstance(delta['tool_calls'], list))
                                or (delta.get('function_call') is not None and not isinstance(delta['function_call'], dict))):
                            raise invalid_response()
                        if reason == 'length':
                            raise Problem('MODEL_OUTPUT_TRUNCATED', '模型输出达到长度限制，不能视作完整回答。', 502)
                        if reason == 'content_filter':
                            raise Problem('MODEL_PROVIDER_FILTERED', '模型输出被过滤，不能视作完整回答。', 502)
                        if (reason in ('tool_calls', 'function_call') or delta.get('tool_calls')
                                or delta.get('function_call') is not None):
                            raise Problem('MODEL_PROVIDER_UNSUPPORTED_OUTPUT', '当前协议不支持工具调用输出。', 502)
                        if delta.get('refusal'):
                            raise Problem('MODEL_PROVIDER_REFUSED', '模型拒绝了本次请求。', 502)
                        if reason not in (None, 'stop'):
                            raise invalid_response()
                        stopped = reason == 'stop'
                        if content:
                            try:
                                content.encode('utf-8')
                            except UnicodeEncodeError:
                                raise invalid_response() from None
                            yield content
                    raise Problem('MODEL_PROVIDER_INCOMPLETE_STREAM', '模型流在成功终止前断开。', 502)
        except httpx.TimeoutException as exc:
            raise Problem('MODEL_PROVIDER_TIMEOUT', '模型 Provider 响应超时。', 504) from exc
        except httpx.HTTPStatusError as exc:
            raise Problem('MODEL_PROVIDER_REJECTED', '模型 Provider 拒绝了请求。', 502) from exc
        except httpx.HTTPError as exc:
            raise Problem('MODEL_PROVIDER_UNAVAILABLE', '模型 Provider 当前不可用。', 503) from exc


class ProviderAdapterRegistry:
    """A closed factory: unknown protocols fail instead of silently falling back."""

    def __init__(self):
        self._adapters = {'openai_compatible': OpenAIChatCompletionsAdapter()}

    def status_for(self, provider_type: str) -> str:
        adapter = self._adapters.get(provider_type)
        return adapter.adapter_status if adapter else 'not_implemented'

    def require(self, provider_type: str) -> ProviderAdapter:
        adapter = self._adapters.get(provider_type)
        if not adapter:
            raise Problem('PROVIDER_ADAPTER_NOT_IMPLEMENTED', '该 Provider 协议尚未实现，系统不会自动切换模型。', 409)
        return adapter
