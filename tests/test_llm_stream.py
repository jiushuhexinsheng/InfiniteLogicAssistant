# -*- coding: utf-8 -*-
"""core/llm/stream.py — SSE 解析与 payload/工具调用累积"""
import json

import httpx
import pytest

from core.llm.stream import (
    _accumulate_tool_calls,
    _build_payload,
    _to_anthropic_messages,
    _to_gemini_contents,
    stream_chat,
)


def _sse(chunks) -> bytes:
    """chunk dict 列表 → OpenAI SSE 字节流（含 [DONE]）。"""
    lines = [f"data: {json.dumps(c, ensure_ascii=False)}" for c in chunks]
    lines.append("data: [DONE]")
    return ("\n\n".join(lines) + "\n\n").encode("utf-8")


def _client_for(payload_bytes: bytes, status: int = 200) -> httpx.AsyncClient:
    def handler(request):
        return httpx.Response(status, content=payload_bytes, headers={"Content-Type": "text/event-stream"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_build_payload_includes_tools():
    tools = [{"type": "function", "function": {"name": "x"}}]
    payload = _build_payload({"model": "m", "temperature": 0.5, "max_tokens": 100}, [], tools)
    assert payload["model"] == "m"
    assert payload["stream"] is True
    assert payload["tools"] == tools
    assert payload["tool_choice"] == "auto"


def test_build_payload_no_tools():
    payload = _build_payload({"model": "m"}, [])
    assert "tools" not in payload
    assert "tool_choice" not in payload


def test_accumulate_tool_calls_merges_deltas():
    buf = {}
    _accumulate_tool_calls(buf, {"index": 0, "id": "call_1", "function": {"name": "get_", "arguments": '{"city"'}})
    _accumulate_tool_calls(buf, {"index": 0, "function": {"name": "datetime", "arguments": ':"北京"}'}})
    slot = buf[0]
    assert slot["id"] == "call_1"
    assert slot["function"]["name"] == "get_datetime"
    assert slot["function"]["arguments"] == '{"city":"北京"}'


@pytest.mark.asyncio
async def test_stream_chat_parses_content_and_reasoning():
    client = _client_for(_sse([
        {"choices": [{"delta": {"reasoning_content": "思考中"}}]},
        {"choices": [{"delta": {"content": "你好"}}]},
        {"choices": [{"delta": {"content": "世界"}}]},
    ]))
    events = [e async for e in stream_chat([], client=client)]
    deltas = [(e["type"], e.get("text")) for e in events if e["type"] in ("content_delta", "reasoning_delta")]
    assert ("reasoning_delta", "思考中") in deltas
    assert ("content_delta", "你好") in deltas
    assert ("content_delta", "世界") in deltas
    done = events[-1]
    assert done["type"] == "done"
    assert done["message"]["content"] == "你好世界"
    assert done["message"]["reasoning_content"] == "思考中"


@pytest.mark.asyncio
async def test_stream_chat_accumulates_tool_calls():
    client = _client_for(_sse([
        {"choices": [{"delta": {"tool_calls": [
            {"index": 0, "id": "c1", "function": {"name": "calculate", "arguments": '{"expression"'}}]}}]},
        {"choices": [{"delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": ':"1+1"}'}}]}}]},
    ]))
    events = [e async for e in stream_chat([], client=client)]
    done = events[-1]
    assert done["message"]["tool_calls"][0]["function"]["name"] == "calculate"
    assert done["message"]["tool_calls"][0]["function"]["arguments"] == '{"expression":"1+1"}'


@pytest.mark.asyncio
async def test_stream_chat_http_error_raises():
    client = _client_for(b"", status=500)
    with pytest.raises(httpx.HTTPStatusError):
        async for _ in stream_chat([], client=client):
            pass


@pytest.mark.asyncio
async def test_stream_chat_emits_usage():
    # usage 在末尾的 usage-only chunk（无 choices），不应被跳过
    client = _client_for(_sse([
        {"choices": [{"delta": {"content": "你好"}}]},
        {"usage": {"prompt_tokens": 10, "total_tokens": 12}},
    ]))
    events = [e async for e in stream_chat([], client=client)]
    assert {"type": "usage", "usage": {"prompt_tokens": 10, "total_tokens": 12}} in events
    assert events[-1]["type"] == "done"


# ─── compat 开关：stream_options / max_tokens_field ───

def test_build_payload_compat_stream_options_off():
    payload = _build_payload({"model": "m", "compat": {"stream_options": False}}, [])
    assert payload["stream"] is True
    assert "stream_options" not in payload


def test_build_payload_compat_max_tokens_field():
    payload = _build_payload({"model": "m", "max_tokens": 100, "compat": {"max_tokens_field": "max_completion_tokens"}}, [])
    assert "max_tokens" not in payload
    assert payload["max_completion_tokens"] == 100


def test_build_payload_default_compat_preserves_behavior():
    # 默认 compat 与既有行为一致：max_tokens + stream_options.include_usage
    payload = _build_payload({"model": "m", "max_tokens": 100}, [])
    assert payload["max_tokens"] == 100
    assert payload["stream_options"] == {"include_usage": True}


# ─── Anthropic Messages 适配器 ───

def _anthropic_sse(events: list[tuple[str, dict]]) -> bytes:
    lines = []
    for etype, data in events:
        lines.append(f"event: {etype}")
        lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    return ("\n\n".join(lines) + "\n\n").encode("utf-8")


_ANTHROPIC_PROFILE = {
    "provider": "anthropic", "endpoint": "https://api.anthropic.com", "chat_path": "/v1/messages",
    "model": "claude-sonnet-4-20250514", "api_key": "k", "max_tokens": 4096,
}


def test_to_anthropic_messages_merges_consecutive_tools():
    out = _to_anthropic_messages([
        {"role": "user", "content": "算一下"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "a", "function": {"name": "f1", "arguments": "{}"}},
            {"id": "b", "function": {"name": "f2", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "a", "content": "r1"},
        {"role": "tool", "tool_call_id": "b", "content": "r2"},
    ])
    # assistant 消息含两个 tool_use block；两个 tool 结果合并为一条 user tool_result
    assert out[1]["role"] == "assistant"
    assert [b["type"] for b in out[1]["content"]] == ["tool_use", "tool_use"]
    last = out[-1]
    assert last["role"] == "user"
    assert [b["type"] for b in last["content"]] == ["tool_result", "tool_result"]
    assert last["content"][0]["tool_use_id"] == "a"


@pytest.mark.asyncio
async def test_stream_anthropic_text_thinking_tool_usage():
    client = _client_for(_anthropic_sse([
        ("message_start", {"type": "message_start", "message": {"content": [], "usage": {"input_tokens": 10}} }),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "你好"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("content_block_start", {"type": "content_block_start", "index": 1, "content_block": {"type": "thinking", "thinking": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 1, "delta": {"type": "thinking_delta", "thinking": "思考中"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 1}),
        ("content_block_start", {"type": "content_block_start", "index": 2, "content_block": {"type": "tool_use", "id": "toolu_01", "name": "calculate", "input": {}}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": '{"expression"'}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": ':"1+1"}'}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 2}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 20}}),
        ("message_stop", {"type": "message_stop"}),
    ]))
    events = [e async for e in stream_chat([], profile=_ANTHROPIC_PROFILE, client=client)]
    deltas = [(e["type"], e.get("text")) for e in events if e["type"] in ("content_delta", "reasoning_delta")]
    assert ("content_delta", "你好") in deltas
    assert ("reasoning_delta", "思考中") in deltas
    # usage 映射为 OpenAI 风格
    usage = [e["usage"] for e in events if e["type"] == "usage"]
    assert usage and usage[0] == {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
    done = events[-1]
    assert done["type"] == "done"
    assert done["message"]["content"] == "你好"
    assert done["message"]["reasoning_content"] == "思考中"
    tc = done["message"]["tool_calls"][0]
    assert tc["function"]["name"] == "calculate"
    assert tc["function"]["arguments"] == '{"expression":"1+1"}'


# ─── Gemini 适配器 ───

def _gemini_sse(chunks: list[dict]) -> bytes:
    lines = [f"data: {json.dumps(c, ensure_ascii=False)}" for c in chunks]
    return ("\n\n".join(lines) + "\n\n").encode("utf-8")


_GEMINI_PROFILE = {
    "provider": "gemini", "endpoint": "https://generativelanguage.googleapis.com",
    "chat_path": "/v1beta/models/{model}:streamGenerateContent?alt=sse",
    "model": "gemini-2.5-flash", "api_key": "k", "max_tokens": 4096,
}


def test_to_gemini_contents_function_response_names():
    out = _to_gemini_contents([
        {"role": "user", "content": "天气"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_1", "function": {"name": "get_weather", "arguments": '{"city":"北京"}'}},
        ]},
        {"role": "tool", "tool_call_id": "call_1", "content": "晴"},
    ])
    model = out[1]
    assert model["parts"][0]["functionCall"]["name"] == "get_weather"
    resp = out[-1]
    assert resp["role"] == "user"
    assert resp["parts"][0]["functionResponse"]["name"] == "get_weather"
    assert resp["parts"][0]["functionResponse"]["response"]["result"] == "晴"


@pytest.mark.asyncio
async def test_stream_gemini_text_thought_tool_usage():
    client = _client_for(_gemini_sse([
        {"candidates": [{"content": {"role": "model", "parts": [{"text": "你好"}]}}], "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 15}},
        {"candidates": [{"content": {"role": "model", "parts": [{"thought": True, "text": "思考中"}]}}]},
        {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": "get_weather", "args": {"city": "北京"}}}]}}]},
    ]))
    events = [e async for e in stream_chat([], profile=_GEMINI_PROFILE, client=client)]
    deltas = [(e["type"], e.get("text")) for e in events if e["type"] in ("content_delta", "reasoning_delta")]
    assert ("content_delta", "你好") in deltas
    assert ("reasoning_delta", "思考中") in deltas
    usage = [e["usage"] for e in events if e["type"] == "usage"]
    assert usage and usage[0] == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    done = events[-1]
    tc = done["message"]["tool_calls"][0]
    assert tc["function"]["name"] == "get_weather"
    assert "北京" in tc["function"]["arguments"]
