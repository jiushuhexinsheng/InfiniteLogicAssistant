# -*- coding: utf-8 -*-
"""OpenAI 兼容协议:chat/completions SSE 解析。OpenAI-compatible protocol: chat/completions SSE parsing.

请求体/请求头/stream_options 兼容开关见 _build_payload/_headers。
"""
import json
from collections.abc import AsyncIterator

import httpx

# ─────────────────────────── OpenAI 兼容 ───────────────────────────

def _build_payload(profile: dict, messages: list, tools=None) -> dict:
    """构建 OpenAI 兼容请求体（含 stream_options / max_tokens 字段兼容开关）。Build an OpenAI-compatible request payload (with stream_options / max_tokens field compatibility toggles).

    Args:
        profile: LLM profile 配置。LLM profile config.
        messages: 对话消息列表。Conversation messages.
        tools: 可选工具定义。Optional tool definitions.

    Returns:
        POST 请求体 dict。The POST request body dict.
    """
    compat = profile.get("compat") or {}
    payload: dict = {
        "model": profile.get("model", ""),
        "messages": messages,
        "temperature": profile.get("temperature", 0.7),
        "stream": True,
    }
    # 部分网关/推理模型用 max_completion_tokens；旧格式只认 max_tokens
    max_tokens_field = compat.get("max_tokens_field", "max_tokens")
    payload[max_tokens_field] = profile.get("max_tokens", 4096)
    # 部分网关拒绝未知字段 stream_options.include_usage（如 Ollama/LM Studio）
    if compat.get("stream_options", True):
        payload["stream_options"] = {"include_usage": True}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    return payload

def _headers(profile: dict) -> dict:
    """构造 OpenAI 风格请求头（Bearer 鉴权）。Build OpenAI-style request headers (Bearer auth).

    Args:
        profile: LLM profile 配置。LLM profile config.

    Returns:
        请求头 dict。The headers dict.
    """
    h = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if profile.get("api_key"):
        h["Authorization"] = f"Bearer {profile['api_key']}"
    return h

def _accumulate_tool_calls(buffer: dict, tc: dict) -> None:
    """按 index 累加流式 tool_call 分片（id / name / arguments 拼接）。Accumulate streaming tool_call fragments by index (concatenating id / name / arguments).

    Args:
        buffer: index → 工具调用槽位 的累积字典。Buffer mapping index → tool-call slot.
        tc: 单个 delta 中的 tool_call 分片。A tool_call fragment from a single delta.
    """
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

async def _stream_openai(
    messages: list[dict],
    tools: list[dict] | None,
    profile: dict,
    client: httpx.AsyncClient | None,
) -> AsyncIterator[dict]:
    """OpenAI chat/completions SSE 解析。Parse the OpenAI chat/completions SSE stream.

    Args:
        messages: 对话消息列表。Conversation messages.
        tools: 可选工具定义。Optional tool definitions.
        profile: LLM profile 配置。LLM profile config.
        client: 可复用的 httpx 客户端（None 时自建并在结束时关闭）。Reusable httpx client (created and closed internally when None).

    Yields:
        协议无关的事件 dict。Protocol-agnostic event dicts.
    """
    url = f"{profile.get('endpoint', '').rstrip('/')}{(profile.get('chat_path') or '/v1/chat/completions')}"
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
                # usage 常在末尾的 usage-only chunk 出现（无 choices），须在跳过前取出
                usage = chunk.get("usage")
                if usage:
                    yield {"type": "usage", "usage": usage}
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

