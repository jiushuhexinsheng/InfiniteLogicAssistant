# -*- coding: utf-8 -*-
"""execute_task 拆分出的私有步骤单测。

execute_task 原先是一个 286 行的巨型函数，工具分流/流式解析/历史播种都无法单独
覆盖。拆分后这些步骤各自纯化（或只依赖注入的协作者），本文件直接钉住它们：
`_seed_history` 的提示拼装、`_load_context` 的 fail-open、`_stream_turn` 的
停止/暂停/正常三态、`_run_tool_calls` 的并发分流、`_apply_tool_results` 的顺序与落库。

Unit tests for the private steps extracted from execute_task: prompt assembly, fail-open
context loading, the stopped/paused/normal outcomes of one streamed turn, the tool
dispatch split, and ordered result persistence.
"""
import asyncio
import json

import pytest

import core.orchestrator.executor as ex
from core.orchestrator.confirm import ConfirmResult
from core.orchestrator.control import CancellationToken, PauseController, PauseMode
from core.orchestrator.executor import (
    _apply_tool_results,
    _load_context,
    _run_tool_calls,
    _seed_history,
    _stream_turn,
)
from core.orchestrator.session import Session
from core.orchestrator.task import Task
from core.prompts import RAG_CITE_NOTE


class _FakeLLM:
    """按脚本回放事件的假 LLM 客户端。A fake LLM client replaying scripted events."""

    def __init__(self, events):
        self.events = events

    def retry_stream_chat(self, messages, tools=None):
        async def gen():
            for evt in self.events:
                yield evt
        return gen()


def test_seed_history_builds_system_and_first_user_message():
    """system 提示含上下文与最近对话，首条用户消息带参数；当前轮不重复进 system。"""
    s = Session()
    s.append("user", "之前的问题")
    s.append("assistant", "之前的回答")
    s.append("user", "当前问题")

    history = _seed_history(Task("t", "当前问题", params={"path": "a.txt"}), s, "【相关】env", [])

    assert history[0]["role"] == "system"
    assert "【相关】env" in history[0]["content"]
    assert "之前的问题" in history[0]["content"]
    assert "之前的回答" in history[0]["content"]
    assert "当前问题" not in history[0]["content"], "当前轮不应作为历史进 system"
    assert history[1] == {
        "role": "user",
        "content": '当前问题\n参考参数：{"path": "a.txt"}',
    }


def test_seed_history_cite_note_only_with_sources():
    """有编号命中才附引用标注尾注（docs/designs/05 §3.1）。"""
    s = Session()
    s.append("user", "q")
    with_sources = _seed_history(
        Task("t", "q"), s, "", [{"path": "a.md", "section": "s", "score": 1.0}])
    without = _seed_history(Task("t", "q"), s, "", [])

    assert RAG_CITE_NOTE in with_sources[0]["content"]
    assert RAG_CITE_NOTE not in without[0]["content"]


@pytest.mark.asyncio
async def test_load_context_is_fail_open(monkeypatch):
    """上下文加载失败返回空值，绝不阻断执行。Context failures never block execution."""

    async def ok(query):
        return "ctx", [{"path": "x.md"}]

    monkeypatch.setattr(ex, "build_context_with_sources", ok)
    assert await _load_context(Task("t", "q")) == ("ctx", [{"path": "x.md"}])

    async def boom(query):
        raise RuntimeError("rag down")

    monkeypatch.setattr(ex, "build_context_with_sources", boom)
    assert await _load_context(Task("t", "q")) == ("", [])


@pytest.mark.asyncio
async def test_stream_turn_reports_stopped_mid_stream(monkeypatch):
    """流中途取消 → stopped 态，且取消后的增量不再消费。"""
    token = CancellationToken()

    class _StopLLM:
        def retry_stream_chat(self, messages, tools=None):
            async def gen():
                yield {"type": "content_delta", "text": "第一段。"}
                token.cancel()
                yield {"type": "content_delta", "text": "不应出现"}
            return gen()

    monkeypatch.setattr(ex, "get_llm_client", lambda: _StopLLM())
    events: asyncio.Queue = asyncio.Queue()
    turn = await _stream_turn([], token, None, events)

    assert turn.stopped is True
    assert turn.paused is False
    shown = "".join(e.get("text", "") for e in _drain(events) if e["type"] == "content_delta")
    assert "不应出现" not in shown


@pytest.mark.asyncio
async def test_stream_turn_pause_abort_returns_partial(monkeypatch):
    """safe stop → paused 态并带回已生成部分，供恢复后续写。"""
    pause = PauseController()

    class _PauseLLM:
        def retry_stream_chat(self, messages, tools=None):
            async def gen():
                yield {"type": "content_delta", "text": "部分内容"}
                pause.pause(PauseMode.SAFE_STOP)
                yield {"type": "content_delta", "text": "不应出现"}
            return gen()

    monkeypatch.setattr(ex, "get_llm_client", lambda: _PauseLLM())
    turn = await _stream_turn([], CancellationToken(), pause, None)

    assert turn.paused is True
    assert turn.stopped is False
    assert "部分内容" in turn.partial
    assert "不应出现" not in turn.partial


@pytest.mark.asyncio
async def test_stream_turn_normalizes_final_message_without_deltas(monkeypatch):
    """无流式增量时回落到最终消息解析，assistant 消息内容归一化。"""
    monkeypatch.setattr(ex, "get_llm_client", lambda: _FakeLLM([
        {"type": "done", "message": {"role": "assistant", "content": "回答了"}},
    ]))
    turn = await _stream_turn([], CancellationToken(), None, None)

    assert turn.paused is False and turn.stopped is False
    assert turn.message == {"role": "assistant", "content": "回答了"}
    assert isinstance(turn.speech, str)


@pytest.mark.asyncio
async def test_run_tool_calls_allowed_concurrent_asked_serial(monkeypatch):
    """免确认工具先并发跑完，需确认工具再串行；结果按原始下标返回。"""
    from core.tools.policy import Decision

    order: list[str] = []
    inflight = 0
    max_inflight = 0

    async def fake_acall(name, args, cancel=None, session=None):
        nonlocal inflight, max_inflight
        order.append(name)
        inflight += 1
        max_inflight = max(max_inflight, inflight)
        await asyncio.sleep(0.02)
        inflight -= 1
        return f"ok:{name}"

    async def fake_confirm(session, name, args):
        return ConfirmResult(True)  # 放行。Allowed.

    monkeypatch.setattr(ex.TOOLS, "acall", fake_acall)
    monkeypatch.setattr(ex, "confirm_tool", fake_confirm)
    monkeypatch.setattr(ex, "decide",
                        lambda name: Decision("allow" if name == "a" else "ask", "test"))

    tool_calls = [
        {"id": "c1", "function": {"name": "a", "arguments": json.dumps({"x": 1})}},
        {"id": "c2", "function": {"name": "b", "arguments": "{}"}},
    ]
    results = await _run_tool_calls(tool_calls, 0, Session(), CancellationToken(), None, None)

    assert sorted(results) == [0, 1]
    assert [results[i][0]["tool"] for i in sorted(results)] == ["a", "b"]
    assert results[0][1]["tool_call_id"] == "c1"
    assert results[1][1]["content"] == "ok:b"
    assert order == ["a", "b"], "先并发免确认、后串行需确认"
    assert max_inflight == 1, "仅一个免确认工具，不应并发"


def test_apply_tool_results_keeps_call_order_and_records_blocks():
    """按原始顺序落 steps/history；会话里写 tool 块并保留完整长度。"""
    s = Session()
    steps: list[dict] = []
    history: list[dict] = []
    results = {
        1: ({"step": 0, "tool": "b", "status": "ok", "result": "rb"},
            {"role": "tool", "tool_call_id": "c2", "content": "B" * 20}, "B-feed"),
        0: ({"step": 0, "tool": "a", "status": "ok", "result": "ra"},
            {"role": "tool", "tool_call_id": "c1", "content": "A"}, "A-feed"),
    }

    _apply_tool_results(results, steps, history, s)

    assert [x["tool"] for x in steps] == ["a", "b"]
    assert [m["content"] for m in history] == ["A-feed", "B-feed"]
    blocks = [b for m in s.messages for b in m.get("blocks", [])]
    assert [b["payload"]["name"] for b in blocks] == ["a", "b"]
    assert blocks[1]["payload"]["full_len"] == 20


def _drain(q: asyncio.Queue) -> list[dict]:
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out
