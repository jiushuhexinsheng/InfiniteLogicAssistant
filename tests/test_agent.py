# -*- coding: utf-8 -*-
"""core/agent.py — 历史裁剪 + ReAct 循环（用假 LLM 客户端，无网络）"""
import pytest

from core.agent import _trim_history, run_agent
from core.llm.client import CircuitBreakerOpenError


class _FakeLlm:
    """每次调用弹出一条预置的事件序列。"""

    def __init__(self, script):
        self.script = script
        self.calls = []  # 记录每次收到的 messages

    def retry_stream_chat(self, messages, tools=None):
        async def gen():
            self.calls.append(messages)
            for evt in self.script.pop(0):
                yield evt

        return gen()


def _done_with_tool(name: str, arguments: str = "{}", call_id: str = "call_1") -> dict:
    return {
        "type": "done",
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}],
        },
    }


# ─── 历史裁剪 ───

def test_trim_history_keeps_within_limit_unchanged():
    msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "u"}]
    assert _trim_history(msgs, 40) == msgs


def test_trim_history_keeps_system_and_tail():
    msgs = [{"role": "system", "content": "S"}] + [{"role": "user", "content": str(i)} for i in range(20)]
    out = _trim_history(msgs, 10)
    assert out[0]["role"] == "system"
    assert len(out) == 10
    assert out[-1]["content"] == "19"


def test_trim_history_pops_leading_tool_messages():
    msgs = [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "tool", "content": "t1"},
        {"role": "tool", "content": "t2"},
        {"role": "assistant", "content": "a2"},
    ]
    out = _trim_history(msgs, 4)
    assert out[0]["role"] == "system"
    assert out[1]["role"] == "assistant" and out[1]["content"] == "a2"
    # 不能以 tool 消息开头（会切断 tool_call↔tool 配对）
    assert not any(m.get("tool_call_id") for m in out)


# ─── ReAct 循环 ───

@pytest.mark.asyncio
async def test_run_agent_simple_reply(monkeypatch):
    fake = _FakeLlm([
        [
            {"type": "content_delta", "text": "你好"},
            {"type": "done", "message": {"role": "assistant", "content": "你好"}},
        ]
    ])
    monkeypatch.setattr("core.agent.legacy.get_llm_client", lambda: fake)
    events = [e async for e in run_agent([{"role": "user", "content": "hi"}])]
    assert events[0] == {"type": "content_delta", "text": "你好"}
    assert events[-1] == {"type": "done"}


@pytest.mark.asyncio
async def test_run_agent_executes_tool_and_feeds_back(monkeypatch):
    fake = _FakeLlm([
        [_done_with_tool("get_datetime")],
        [
            {"type": "content_delta", "text": "现在时间是..."},
            {"type": "done", "message": {"role": "assistant", "content": "现在时间是..."}},
        ],
    ])
    monkeypatch.setattr("core.agent.legacy.get_llm_client", lambda: fake)
    events = [e async for e in run_agent([{"role": "user", "content": "几点了"}])]

    assert any(e["type"] == "tool_start" and e["name"] == "get_datetime" for e in events)
    tool_end = next(e for e in events if e["type"] == "tool_end")
    assert tool_end["status"] == "ok"
    assert events[-1] == {"type": "done"}
    # 第二轮已回喂 tool 消息
    fed = fake.calls[1]
    assert any(m["role"] == "tool" and m["tool_call_id"] == "call_1" for m in fed)


@pytest.mark.asyncio
async def test_run_agent_tool_error_status(monkeypatch):
    fake = _FakeLlm([
        [_done_with_tool("no_such_tool")],
        [{"type": "done", "message": {"role": "assistant", "content": "失败了"}}],
    ])
    monkeypatch.setattr("core.agent.legacy.get_llm_client", lambda: fake)
    events = [e async for e in run_agent([{"role": "user", "content": "x"}])]
    tool_end = next(e for e in events if e["type"] == "tool_end")
    assert tool_end["name"] == "no_such_tool"
    assert tool_end["status"] == "error"
    assert "Error" in tool_end["output"]


@pytest.mark.asyncio
async def test_run_agent_bad_json_args_falls_back_to_empty(monkeypatch):
    fake = _FakeLlm([
        [_done_with_tool("get_datetime", arguments="not-json")],
        [{"type": "done", "message": {"role": "assistant", "content": "ok"}}],
    ])
    monkeypatch.setattr("core.agent.legacy.get_llm_client", lambda: fake)
    events = [e async for e in run_agent([{"role": "user", "content": "x"}])]
    tool_start = next(e for e in events if e["type"] == "tool_start")
    assert tool_start["args"] == {}


@pytest.mark.asyncio
async def test_run_agent_passes_usage(monkeypatch):
    fake = _FakeLlm([
        [
            {"type": "content_delta", "text": "ok"},
            {"type": "usage", "usage": {"total_tokens": 12}},
            {"type": "done", "message": {"role": "assistant", "content": "ok"}},
        ]
    ])
    monkeypatch.setattr("core.agent.legacy.get_llm_client", lambda: fake)
    events = [e async for e in run_agent([{"role": "user", "content": "x"}])]
    assert {"type": "usage", "usage": {"total_tokens": 12}} in events
    assert events[-1] == {"type": "done"}


@pytest.mark.asyncio
async def test_run_agent_breaker_open(monkeypatch):
    class _Boom:
        def retry_stream_chat(self, messages, tools=None):
            raise CircuitBreakerOpenError()

    monkeypatch.setattr("core.agent.legacy.get_llm_client", lambda: _Boom())
    events = [e async for e in run_agent([{"role": "user", "content": "x"}])]
    assert events[0] == {"type": "error", "message": "服务暂时不可用，请稍后重试"}


@pytest.mark.asyncio
async def test_run_agent_recursion_limit(monkeypatch):
    # run_agent 的内层 async for 依赖生成器自然结束；每次调用只 yield 一个 done（带工具调用）
    class _Fake:
        def retry_stream_chat(self, messages, tools=None):
            async def gen():
                yield _done_with_tool("get_datetime")

            return gen()

    monkeypatch.setattr("core.agent.legacy.get_llm_client", lambda: _Fake())
    events = [e async for e in run_agent([{"role": "user", "content": "x"}])]
    assert events[-1]["type"] == "error"
    assert "上限" in events[-1]["message"]
