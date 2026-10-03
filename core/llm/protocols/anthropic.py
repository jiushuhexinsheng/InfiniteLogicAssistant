# -*- coding: utf-8 -*-
"""Anthropic Messages 协议:SSE(text/thinking/tool_use)→ 内部事件。

Anthropic Messages protocol: SSE (text/thinking/tool_use) → internal events.
"""
import json
from collections.abc import AsyncIterator

import httpx

from .common import _raise_for_status_read, _split_system

# ─────────────────────────── Anthropic Messages ───────────────────────────



def _to_anthropic_messages(messages: list[dict]) -> list[dict]:
    """OpenAI 消息 → Anthropic messages（system 已拆走；连续 tool 消息合并为一个 tool_result 用户消息）。Convert OpenAI messages → Anthropic messages (system already split out; consecutive tool messages merged into one tool_result user message)."""
    out: list[dict] = []
    for m in messages:
        role = m.get("role")
        if role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": m.get("tool_call_id") or "",
                "content": str(m.get("content") or ""),
            }
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
        elif role == "assistant":
            blocks: list[dict] = []
            content = m.get("content") or ""
            if content:
                blocks.append({"type": "text", "text": content})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                raw = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw) if isinstance(raw, str) else raw
                except json.JSONDecodeError:
                    args = {}
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id") or "",
                    "name": fn.get("name") or "",
                    "input": args,
                })
            if not blocks:
                continue
            if len(blocks) == 1 and blocks[0]["type"] == "text":
                out.append({"role": "assistant", "content": blocks[0]["text"]})
            else:
                out.append({"role": "assistant", "content": blocks})
        elif role == "user":
            text = str(m.get("content") or "")
            # tool_result 用户消息后追加文本：并入同一用户消息（Anthropic 要求）
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append({"type": "text", "text": text})
            else:
                out.append({"role": "user", "content": text})
    return out

def _to_anthropic_tools(tools: list[dict] | None) -> list[dict]:
    """OpenAI 工具定义 → Anthropic tools（input_schema）。Convert OpenAI tool definitions → Anthropic tools (input_schema).

    Args:
        tools: 可选 OpenAI 风格工具定义。Optional OpenAI-style tool definitions.

    Returns:
        Anthropic 风格工具列表。The Anthropic-style tool list.
    """
    return [
        {
            "name": (t.get("function") or {}).get("name") or "",
            "description": (t.get("function") or {}).get("description") or "",
            "input_schema": (t.get("function") or {}).get("parameters") or {"type": "object", "properties": {}},
        }
        for t in tools or []
    ]

def _build_anthropic_payload(profile: dict, messages: list, system: str, tools: list[dict] | None) -> dict:
    """构建 Anthropic Messages API 请求体。Build an Anthropic Messages API request payload.

    Args:
        profile: LLM profile 配置。LLM profile config.
        messages: 已拆分 system 的对话消息。Conversation messages with system already split out.
        system: system 提示文本（可能为空）。System prompt text (may be empty).
        tools: 可选工具定义。Optional tool definitions.

    Returns:
        POST 请求体 dict。The POST request body dict.
    """
    payload: dict = {
        "model": profile.get("model") or "",
        "max_tokens": profile.get("max_tokens", 4096),
        "messages": _to_anthropic_messages(messages),
        "stream": True,
    }
    t = profile.get("temperature")
    if t is not None:
        payload["temperature"] = t
    if system:
        payload["system"] = system
    if tools:
        payload["tools"] = _to_anthropic_tools(tools)
    return payload

def _anthropic_usage(u: dict) -> dict:
    """Anthropic usage → 内部 OpenAI 风格 usage（供 TokenUsage 消费）。Map Anthropic usage → internal OpenAI-style usage (consumed by TokenUsage)."""
    inp = u.get("input_tokens") or 0
    out = u.get("output_tokens") or 0
    return {"prompt_tokens": inp, "completion_tokens": out, "total_tokens": inp + out}

async def _stream_anthropic(
    messages: list[dict],
    tools: list[dict] | None,
    profile: dict,
    client: httpx.AsyncClient | None,
) -> AsyncIterator[dict]:
    """Anthropic Messages API SSE（text / thinking / tool_use）→ 内部事件。Parse the Anthropic Messages API SSE (text / thinking / tool_use) into internal events.

    Args:
        messages: 对话消息列表。Conversation messages.
        tools: 可选工具定义。Optional tool definitions.
        profile: LLM profile 配置。LLM profile config.
        client: 可复用的 httpx 客户端（None 时自建并在结束时关闭）。Reusable httpx client (created and closed internally when None).

    Yields:
        协议无关的事件 dict。Protocol-agnostic event dicts.
    """
    system, msgs = _split_system(messages)
    payload = _build_anthropic_payload(profile, msgs, system, tools)
    url = f"{profile.get('endpoint', '').rstrip('/')}{(profile.get('chat_path') or '/v1/messages')}"
    timeout = float(profile.get("timeout", 60) or 60)
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "anthropic-version": "2023-06-01",
    }
    if profile.get("api_key"):
        headers["x-api-key"] = profile["api_key"]

    content_buf: list[str] = []
    reasoning_buf: list[str] = []
    tool_blocks: dict = {}   # index → {id, name, json: [chunks]}
    usage_in = 0             # message_start 携带 input_tokens
    usage_out = 0            # message_delta 携带 output_tokens

    own = None
    if client is None:
        own = httpx.AsyncClient(timeout=timeout)
        client = own
    current_event = ""
    try:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            await _raise_for_status_read(resp)
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    current_event = line[7:].strip()
                    continue
                if not line.startswith("data: "):
                    continue
                try:
                    evt = json.loads(line[6:].strip())
                except json.JSONDecodeError:
                    continue
                etype = evt.get("type") or current_event
                if etype == "message_start":
                    u = (evt.get("message") or {}).get("usage") or {}
                    usage_in = u.get("input_tokens") or 0
                elif etype == "content_block_start":
                    idx = evt.get("index", 0)
                    cb = evt.get("content_block") or {}
                    ctype = cb.get("type")
                    if ctype == "text":
                        content_buf.append(cb.get("text") or "")
                    elif ctype == "thinking":
                        reasoning_buf.append(cb.get("thinking") or "")
                    elif ctype == "tool_use":
                        tool_blocks[idx] = {"id": cb.get("id") or "", "name": cb.get("name") or "", "json": []}
                elif etype == "content_block_delta":
                    idx = evt.get("index", 0)
                    d = evt.get("delta") or {}
                    dtype = d.get("type")
                    if dtype == "text_delta":
                        txt = d.get("text") or ""
                        if txt:
                            content_buf.append(txt)
                            yield {"type": "content_delta", "text": txt}
                    elif dtype == "thinking_delta":
                        txt = d.get("thinking") or ""
                        if txt:
                            reasoning_buf.append(txt)
                            yield {"type": "reasoning_delta", "text": txt}
                    elif dtype == "input_json_delta":
                        blk = tool_blocks.get(idx)
                        if blk is not None:
                            blk["json"].append(d.get("partial_json") or "")
                elif etype == "message_delta":
                    usage = evt.get("usage")
                    if usage:
                        usage_out = usage.get("output_tokens") or 0
                        yield {"type": "usage", "usage": _anthropic_usage({"input_tokens": usage_in, "output_tokens": usage_out})}
                elif etype == "message_stop":
                    break

        tool_calls = []
        for idx in sorted(tool_blocks):
            blk = tool_blocks[idx]
            arguments = "".join(blk["json"]).strip() or "{}"  # 原样累积，与 OpenAI 适配器一致
            tool_calls.append({
                "id": blk["id"], "type": "function",
                "function": {"name": blk["name"], "arguments": arguments},
            })
        message: dict = {"role": "assistant", "content": "".join(content_buf)}
        if reasoning_buf:
            message["reasoning_content"] = "".join(reasoning_buf)
        if tool_calls:
            message["tool_calls"] = tool_calls
        yield {"type": "done", "message": message}
    finally:
        if own is not None:
            await own.aclose()

