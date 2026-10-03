# -*- coding: utf-8 -*-
"""Google Gemini 协议:streamGenerateContent?alt=sse → 内部事件。

Google Gemini protocol: streamGenerateContent?alt=sse → internal events.
"""
import json
from collections.abc import AsyncIterator

import httpx

from .common import _raise_for_status_read, _split_system

# ─────────────────────────── Google Gemini ───────────────────────────

def _gemini_url(profile: dict) -> str:
    """拼接 Gemini streamGenerateContent URL（替换 {model} 占位符）。Build the Gemini streamGenerateContent URL (substituting the {model} placeholder).

    Args:
        profile: LLM profile 配置。LLM profile config.

    Returns:
        完整的请求 URL。The full request URL.
    """
    endpoint = (profile.get("endpoint") or "").rstrip("/")
    path = profile.get("chat_path") or "/v1beta/models/{model}:streamGenerateContent?alt=sse"
    path = path.replace("{model}", profile.get("model") or "")
    return f"{endpoint}{path if path.startswith('/') else '/' + path}"

def _to_gemini_contents(messages: list[dict]) -> list[dict]:
    """OpenAI 消息 → Gemini contents（system 已拆走；连续 user 消息合并 parts）。Convert OpenAI messages → Gemini contents (system already split out; consecutive user messages merged into parts)."""
    fn_by_tool_call_id: dict[str, str] = {}
    contents: list[dict] = []

    def push_user(parts: list[dict]) -> None:
        """向 contents 追加 user parts（与末尾 user 消息合并）。Append user parts to contents (merging with a trailing user message)."""
        if contents and contents[-1]["role"] == "user":
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": "user", "parts": parts})

    for m in messages:
        role = m.get("role")
        if role == "user":
            push_user([{"text": str(m.get("content") or "")}])
        elif role == "assistant":
            parts: list[dict] = []
            content = m.get("content") or ""
            if content:
                parts.append({"text": content})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                fname = fn.get("name") or ""
                raw = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw) if isinstance(raw, str) else raw
                except json.JSONDecodeError:
                    args = {}
                tc_id = tc.get("id") or ""
                if tc_id:
                    fn_by_tool_call_id[tc_id] = fname
                parts.append({"functionCall": {"name": fname, "args": args}})
            contents.append({"role": "model", "parts": parts})
        elif role == "tool":
            fname = fn_by_tool_call_id.get(m.get("tool_call_id") or "", "function")
            push_user([{
                "functionResponse": {"name": fname, "response": {"result": str(m.get("content") or "")}},
            }])
    return contents

def _to_gemini_tools(tools: list[dict] | None) -> list[dict]:
    """OpenAI 工具定义 → Gemini functionDeclarations。Convert OpenAI tool definitions → Gemini functionDeclarations.

    Args:
        tools: 可选 OpenAI 风格工具定义。Optional OpenAI-style tool definitions.

    Returns:
        Gemini 风格 tools 列表。The Gemini-style tools list.
    """
    decls = [
        {
            "name": (t.get("function") or {}).get("name") or "",
            "description": (t.get("function") or {}).get("description") or "",
            "parameters": (t.get("function") or {}).get("parameters") or {"type": "object", "properties": {}},
        }
        for t in tools or []
    ]
    return [{"functionDeclarations": decls}] if decls else []

def _build_gemini_payload(profile: dict, messages: list, tools: list[dict] | None) -> dict:
    """构建 Gemini generateContent 请求体（含 systemInstruction / generationConfig）。Build a Gemini generateContent request payload (incl. systemInstruction / generationConfig).

    Args:
        profile: LLM profile 配置。LLM profile config.
        messages: 对话消息列表。Conversation messages.
        tools: 可选工具定义。Optional tool definitions.

    Returns:
        POST 请求体 dict。The POST request body dict.
    """
    system, msgs = _split_system(messages)
    payload: dict = {"contents": _to_gemini_contents(msgs)}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    gtools = _to_gemini_tools(tools)
    if gtools:
        payload["tools"] = gtools
    payload["generationConfig"] = {
        "temperature": profile.get("temperature", 0.7),
        "maxOutputTokens": profile.get("max_tokens", 4096),
    }
    return payload

def _gemini_usage(u: dict) -> dict:
    """Gemini usageMetadata → 内部 usage。Map Gemini usageMetadata → internal usage.

    Args:
        u: Gemini usageMetadata dict。The Gemini usageMetadata dict.

    Returns:
        内部 OpenAI 风格 usage dict。Internal OpenAI-style usage dict.
    """
    p = u.get("promptTokenCount") or 0
    c = u.get("candidatesTokenCount") or 0
    return {"prompt_tokens": p, "completion_tokens": c, "total_tokens": p + c}

async def _stream_gemini(
    messages: list[dict],
    tools: list[dict] | None,
    profile: dict,
    client: httpx.AsyncClient | None,
) -> AsyncIterator[dict]:
    """Gemini streamGenerateContent?alt=sse → 内部事件。Parse Gemini streamGenerateContent?alt=sse into internal events.

    Args:
        messages: 对话消息列表。Conversation messages.
        tools: 可选工具定义。Optional tool definitions.
        profile: LLM profile 配置。LLM profile config.
        client: 可复用的 httpx 客户端（None 时自建并在结束时关闭）。Reusable httpx client (created and closed internally when None).

    Yields:
        协议无关的事件 dict。Protocol-agnostic event dicts.
    """
    payload = _build_gemini_payload(profile, messages, tools)
    url = _gemini_url(profile)
    timeout = float(profile.get("timeout", 60) or 60)
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if profile.get("api_key"):
        headers["x-goog-api-key"] = profile["api_key"]

    content_buf: list[str] = []
    reasoning_buf: list[str] = []
    tool_buf: dict = {}

    own = None
    if client is None:
        own = httpx.AsyncClient(timeout=timeout)
        client = own
    try:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            await _raise_for_status_read(resp)
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if not data_str or data_str in ("{}", "[DONE]"):
                    continue
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                usage = chunk.get("usageMetadata")
                if usage:
                    yield {"type": "usage", "usage": _gemini_usage(usage)}
                for cand in chunk.get("candidates") or []:
                    for part in (cand.get("content") or {}).get("parts") or []:
                        if "functionCall" in part:
                            fc = part["functionCall"]
                            name = fc.get("name") or ""
                            args = fc.get("args") or {}
                            idx = len(tool_buf)
                            args_str = json.dumps(args, ensure_ascii=False)
                            tool_buf[idx] = {"id": "", "type": "function", "function": {"name": name, "arguments": args_str}}
                            yield {"type": "tool_call_delta", "index": idx, "id": "", "name": name, "arguments": args_str}
                        elif part.get("thought"):
                            txt = part.get("text") or ""
                            if txt:
                                reasoning_buf.append(txt)
                                yield {"type": "reasoning_delta", "text": txt}
                        else:
                            txt = part.get("text") or ""
                            if txt:
                                content_buf.append(txt)
                                yield {"type": "content_delta", "text": txt}

        message: dict = {"role": "assistant", "content": "".join(content_buf)}
        if reasoning_buf:
            message["reasoning_content"] = "".join(reasoning_buf)
        if tool_buf:
            message["tool_calls"] = [tool_buf[i] for i in sorted(tool_buf)]
        yield {"type": "done", "message": message}
    finally:
        if own is not None:
            await own.aclose()

