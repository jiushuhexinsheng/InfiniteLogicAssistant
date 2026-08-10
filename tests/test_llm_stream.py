# -*- coding: utf-8 -*-
"""core/llm/stream.py — SSE 解析与 payload/工具调用累积"""
import json

import httpx
import pytest

from core.llm.stream import _accumulate_tool_calls, _build_payload, stream_chat


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
