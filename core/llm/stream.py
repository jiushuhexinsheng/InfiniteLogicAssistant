# -*- coding: utf-8 -*-
"""异步 LLM 流式客户端 — httpx 解析 SSE → 事件流（参照 InfiniteLogic src/llm.py）

事件:
    content_delta    {"type":"content_delta","text":str}
    reasoning_delta  {"type":"reasoning_delta","text":str}
    tool_call_delta  {"type":"tool_call_delta","index":int,"id":str|None,"name":str,"arguments":str}
    done             {"type":"done","message":{role,content,reasoning_content?,tool_calls?}}
"""
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from core.config import resolve_llm_profile


def _build_payload(profile: dict, messages: list, tools=None) -> dict:
    payload = {
        "model": profile.get("model", ""),
        "messages": messages,
        "temperature": profile.get("temperature", 0.7),
        "max_tokens": profile.get("max_tokens", 4096),
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    return payload


def _headers(profile: dict) -> dict:
    h = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if profile.get("api_key"):
        h["Authorization"] = f"Bearer {profile['api_key']}"
    return h


def _accumulate_tool_calls(buffer: dict, tc: dict) -> None:
    idx = tc.get("index", 0)
    if idx not in buffer:
        buffer[idx] = {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
    slot = buffer[idx]
    if tc.get("id"):
        slot["id"] = tc["id"]
    fn = tc.get("function") or {}
    if fn.get("name"):
        slot["function"]["name"] += fn["name"]
    if fn.get("arguments"):
        slot["function"]["arguments"] += fn["arguments"]


async def stream_chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    *,
    profile: dict | None = None,
    client: httpx.AsyncClient | None = None,
) -> AsyncIterator[dict]:
    """流式调用 LLM，逐 chunk yield 事件；最后 yield done（含完整 message）。"""
    if profile is None:
        _, profile = resolve_llm_profile()
    url = f"{profile.get('endpoint', '').rstrip('/')}{profile.get('chat_path', '/v1/chat/completions')}"
    payload = _build_payload(profile, messages, tools)
    timeout = float(profile.get("timeout", 60) or 60)

    content_buf: list[str] = []
    reasoning_buf: list[str] = []
    tool_buf: dict = {}

    own = None
    if client is None:
        own = httpx.AsyncClient(timeout=timeout)
        client = own
    try:
        async with client.stream("POST", url, headers=_headers(profile), json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}

                reasoning = delta.get("reasoning_content")
                if isinstance(reasoning, str) and reasoning:
                    reasoning_buf.append(reasoning)
                    yield {"type": "reasoning_delta", "text": reasoning}

                content = delta.get("content")
                if isinstance(content, str) and content:
                    content_buf.append(content)
                    yield {"type": "content_delta", "text": content}

                for tc in delta.get("tool_calls") or []:
                    _accumulate_tool_calls(tool_buf, tc)
                    yield {
                        "type": "tool_call_delta",
                        "index": tc.get("index", 0),
                        "id": tc.get("id"),
                        "name": (tc.get("function") or {}).get("name") or "",
                        "arguments": (tc.get("function") or {}).get("arguments") or "",
                    }

        message: dict = {"role": "assistant", "content": "".join(content_buf)}
        if reasoning_buf:
            message["reasoning_content"] = "".join(reasoning_buf)
        if tool_buf:
            message["tool_calls"] = [tool_buf[i] for i in sorted(tool_buf)]
        yield {"type": "done", "message": message}
    finally:
        if own is not None:
            await own.aclose()
