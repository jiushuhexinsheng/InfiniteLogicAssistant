# -*- coding: utf-8 -*-
"""异步 LLM 流式客户端 — httpx 解析 SSE → 事件流（参照 InfiniteLogic src/llm.py）。Asynchronous LLM streaming client — httpx parses SSE into an event stream (ported from InfiniteLogic src/llm.py).

多协议分派（core.vendors.resolve_protocol，按 profile.provider / vendor / chat_path）：
- openai   : POST {endpoint}{chat_path}，OpenAI chat/completions SSE
- anthropic: POST {endpoint}/v1/messages，Anthropic Messages API SSE
- gemini   : POST {endpoint}/v1beta/models/{model}:streamGenerateContent?alt=sse

Protocol dispatch (core.vendors.resolve_protocol, keyed by profile.provider / vendor / chat_path):
- openai   : POST {endpoint}{chat_path}, OpenAI chat/completions SSE
- anthropic: POST {endpoint}/v1/messages, Anthropic Messages API SSE
- gemini   : POST {endpoint}/v1beta/models/{model}:streamGenerateContent?alt=sse

事件（协议无关，消费方不变）:
    content_delta    {"type":"content_delta","text":str}
    reasoning_delta  {"type":"reasoning_delta","text":str}
    tool_call_delta  {"type":"tool_call_delta","index":int,"id":str|None,"name":str,"arguments":str}
    usage            {"type":"usage","usage":{...}}   # 末尾 usage-only chunk
    done             {"type":"done","message":{role,content,reasoning_content?,tool_calls?}}

Events (protocol-agnostic, consumers unchanged):
    content_delta    {"type":"content_delta","text":str}
    reasoning_delta  {"type":"reasoning_delta","text":str}
    tool_call_delta  {"type":"tool_call_delta","index":int,"id":str|None,"name":str,"arguments":str}
    usage            {"type":"usage","usage":{...}}   # trailing usage-only chunk
    done             {"type":"done","message":{role,content,reasoning_content?,tool_calls?}}

各协议的 payload 构建与 SSE 解析拆到 `core/llm/protocols/`（openai / anthropic /
gemini / common）；本模块保留多协议分派入口 `stream_chat` —— 调用方
（`core.llm.client` 等）的 `from core.llm.stream import stream_chat` 零改动。

Per-protocol payload building and SSE parsing live in `core/llm/protocols/`
(openai / anthropic / gemini / common); this module keeps the dispatching entry
point `stream_chat`, so callers (`core.llm.client` etc.) importing from
`core.llm.stream` are unchanged.
"""

from collections.abc import AsyncIterator

import httpx

from core.config import resolve_llm_profile
from core.llm.protocols.anthropic import _stream_anthropic
from core.llm.protocols.gemini import _stream_gemini
from core.llm.protocols.openai import _stream_openai
from core.vendors import resolve_protocol


async def stream_chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    *,
    profile: dict | None = None,
    client: httpx.AsyncClient | None = None,
) -> AsyncIterator[dict]:
    """流式调用 LLM，按协议分派；逐 chunk yield 事件；最后 yield done（含完整 message）。Stream an LLM call, dispatching by protocol; yield events chunk by chunk; finally yield done (with the full message).

    Args:
        messages: 对话消息列表。Conversation messages.
        tools: 可选工具定义。Optional tool definitions.
        profile: 可选 LLM profile（默认取全局配置）。Optional LLM profile (defaults to the global config).
        client: 可复用的 httpx 客户端。Reusable httpx client.

    Yields:
        事件 dict：content_delta / reasoning_delta / tool_call_delta / usage / done。Event dicts: content_delta / reasoning_delta / tool_call_delta / usage / done.
    """
    if profile is None:
        _, profile = resolve_llm_profile()
    protocol = resolve_protocol(profile)
    if protocol == "anthropic":
        async for evt in _stream_anthropic(messages, tools, profile, client):
            yield evt
    elif protocol == "gemini":
        async for evt in _stream_gemini(messages, tools, profile, client):
            yield evt
    else:
        async for evt in _stream_openai(messages, tools, profile, client):
            yield evt
