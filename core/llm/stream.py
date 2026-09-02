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
"""
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from core.config import resolve_llm_profile
from core.vendors import resolve_protocol


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


# ─────────────────────────── Anthropic Messages ───────────────────────────


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """从消息中拆出 system 内容（合并为一段），返回 (system, 其余消息)。Extract the system content from messages (joined into one string), returning (system, remaining messages)."""
    system_parts = [str(m.get("content") or "") for m in messages if m.get("role") == "system"]
    return "\n\n".join(system_parts), [m for m in messages if m.get("role") != "system"]


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
