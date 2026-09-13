"""Protocol-only model-provider adapters for the isolated local chat runtime.

This module deliberately has no configuration storage and no policy decisions.  A
caller must pass a resolved credential and explicitly enable the runtime before
an adapter can make a network request.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from .analysis import Problem


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
        headers = {'Authorization': 'Bearer ' + request.credential, 'Accept': 'text/event-stream'}
        try:
            timeout = httpx.Timeout(connect=10.0, read=90.0, write=20.0, pool=10.0)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
                async with client.stream('POST', endpoint, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith('data:'):
                            continue
                        data = line[5:].strip()
                        if data == '[DONE]':
                            return
                        try:
                            item = json.loads(data)
                            content = item['choices'][0].get('delta', {}).get('content')
                        except (IndexError, KeyError, TypeError, ValueError):
                            continue
                        if isinstance(content, str) and content:
                            yield content
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
