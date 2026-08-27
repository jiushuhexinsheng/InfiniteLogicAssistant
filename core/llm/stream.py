# -*- coding: utf-8 -*-
"""异步 LLM 流式客户端 — httpx 解析 SSE → 事件流（参照 InfiniteLogic src/llm.py）

多协议分派（core.providers.resolve_protocol，按 profile.provider / vendor / chat_path）：
- openai   : POST {endpoint}{chat_path}，OpenAI chat/completions SSE
- anthropic: POST {endpoint}/v1/messages，Anthropic Messages API SSE
- gemini   : POST {endpoint}/v1beta/models/{model}:streamGenerateContent?alt=sse

事件（协议无关，消费方不变）:
    content_delta    {"type":"content_delta","text":str}
    reasoning_delta  {"type":"reasoning_delta","text":str}
    tool_call_delta  {"type":"tool_call_delta","index":int,"id":str|None,"name":str,"arguments":str}
    usage            {"type":"usage","usage":{...}}   # 末尾 usage-only chunk
    done             {"type":"done","message":{role,content,reasoning_content?,tool_calls?}}
"""
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from core.config import resolve_llm_profile
from core.providers import resolve_protocol


# ─────────────────────────── OpenAI 兼容 ───────────────────────────


def _build_payload(profile: dict, messages: list, tools=None) -> dict:
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


async def _stream_openai(
    messages: list[dict],
    tools: list[dict] | None,
    profile: dict,
    client: httpx.AsyncClient | None,
) -> AsyncIterator[dict]:
    """OpenAI chat/completions SSE 解析。"""
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


# ─────────────────────────── Anthropic Messages ───────────────────────────


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    system_parts = [str(m.get("content") or "") for m in messages if m.get("role") == "system"]
    return "\n\n".join(system_parts), [m for m in messages if m.get("role") != "system"]


def _to_anthropic_messages(messages: list[dict]) -> list[dict]:
    """OpenAI 消息 → Anthropic messages（system 已拆走；连续 tool 消息合并为一个 tool_result 用户消息）。"""
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
    return [
        {
            "name": (t.get("function") or {}).get("name") or "",
            "description": (t.get("function") or {}).get("description") or "",
            "input_schema": (t.get("function") or {}).get("parameters") or {"type": "object", "properties": {}},
        }
        for t in tools or []
    ]


def _build_anthropic_payload(profile: dict, messages: list, system: str, tools: list[dict] | None) -> dict:
    payload: dict = {
        "model": profile.get("model") or "",
        "max_tokens": profile.get("max_tokens", 4096),
        "messages": _to_anthropic_messages(messages),
        "stream": True,
    }
    if system:
        payload["system"] = system
    if tools:
        payload["tools"] = _to_anthropic_tools(tools)
    return payload


def _anthropic_usage(u: dict) -> dict:
    """Anthropic usage → 内部 OpenAI 风格 usage（供 TokenUsage 消费）。"""
    inp = u.get("input_tokens") or 0
    out = u.get("output_tokens") or 0
    return {"prompt_tokens": inp, "completion_tokens": out, "total_tokens": inp + out}


async def _stream_anthropic(
    messages: list[dict],
    tools: list[dict] | None,
    profile: dict,
    client: httpx.AsyncClient | None,
) -> AsyncIterator[dict]:
    """Anthropic Messages API SSE（text/thinking/tool_use）→ 内部事件。"""
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
            resp.raise_for_status()
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


# ─────────────────────────── Google Gemini ───────────────────────────


def _gemini_url(profile: dict) -> str:
    endpoint = (profile.get("endpoint") or "").rstrip("/")
    path = profile.get("chat_path") or "/v1beta/models/{model}:streamGenerateContent?alt=sse"
    path = path.replace("{model}", profile.get("model") or "")
    return f"{endpoint}{path if path.startswith('/') else '/' + path}"


def _to_gemini_contents(messages: list[dict]) -> list[dict]:
    """OpenAI 消息 → Gemini contents（system 已拆走；连续 user 消息合并 parts）。"""
    fn_by_tool_call_id: dict[str, str] = {}
    contents: list[dict] = []

    def push_user(parts: list[dict]) -> None:
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
    p = u.get("promptTokenCount") or 0
    c = u.get("candidatesTokenCount") or 0
    return {"prompt_tokens": p, "completion_tokens": c, "total_tokens": p + c}


async def _stream_gemini(
    messages: list[dict],
    tools: list[dict] | None,
    profile: dict,
    client: httpx.AsyncClient | None,
) -> AsyncIterator[dict]:
    """Gemini streamGenerateContent?alt=sse → 内部事件。"""
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
            resp.raise_for_status()
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


# ─────────────────────────── 分派入口 ───────────────────────────


async def stream_chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    *,
    profile: dict | None = None,
    client: httpx.AsyncClient | None = None,
) -> AsyncIterator[dict]:
    """流式调用 LLM，按协议分派；逐 chunk yield 事件；最后 yield done（含完整 message）。"""
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
