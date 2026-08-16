# -*- coding: utf-8 -*-
import json

import pytest

from core.orchestrator.control import CancellationToken
from core.orchestrator.executor import execute_task
from core.orchestrator.session import Session
from core.orchestrator.task import Task


def _done(content=None, tool=None, args="{}"):
    msg = {"role": "assistant", "content": content or ""}
    if tool:
        msg["tool_calls"] = [{"id": "c", "type": "function", "function": {"name": tool, "arguments": args}}]
    return {"type": "done", "message": msg}


class _FakeLLM:
    def __init__(self, script):
        self.script = script

    def retry_stream_chat(self, messages, tools=None):
        async def gen():
            for evt in self.script.pop(0):
                yield evt
        return gen()


class _Channel:
    def __init__(self, answers):
        self.answers = list(answers)

    async def ask(self, q):
        return self.answers.pop(0)

    async def notify(self, text):
        pass


@pytest.mark.asyncio
async def test_execute_converges(monkeypatch):
    fake = _FakeLLM([
        [_done(tool="calculate", args=json.dumps({"expression": "1+1"}))],
        [_done(content="结果是 2")],
    ])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)
    s = Session()
    s.channel = _Channel([])
    r = await execute_task(Task("t", "算 1+1", risk="read"), s, CancellationToken())
    assert r["status"] == "done"
    assert "2" in r["summary"]
    assert any(st["tool"] == "calculate" and st["status"] == "ok" for st in r["steps"])


@pytest.mark.asyncio
async def test_execute_step_limit(monkeypatch):
    class _Fake:
        def retry_stream_chat(self, messages, tools=None):
            async def gen():
                yield _done(tool="calculate", args=json.dumps({"expression": "1"}))
            return gen()
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: _Fake())
    s = Session()
    s.channel = _Channel([])
    r = await execute_task(Task("t", "无限循环", risk="read"), s, CancellationToken())
    assert r["status"] == "failed"
    assert "上限" in r["summary"]


@pytest.mark.asyncio
async def test_execute_cancelled_before(monkeypatch):
    token = CancellationToken()
    token.cancel()
    s = Session()
    s.channel = _Channel([])
    r = await execute_task(Task("t", "x", risk="read"), s, token)
    assert r["status"] == "stopped"


@pytest.mark.asyncio
async def test_execute_uses_coordinator_for_complex(monkeypatch):
    async def fake_coordinator(task, session, cancel):
        return {"status": "done", "summary": "多智能体结果", "subtasks": [
            {"goal": "a", "agent_type": "doer", "status": "done", "output": "ok", "tools": []}]}

    monkeypatch.setattr("core.orchestrator.executor.run_coordinator", fake_coordinator)
    monkeypatch.setattr("core.orchestrator.executor.cfg",
                        lambda path, default=None: True if path == "agent.multi_agent" else default)
    s = Session()
    s.channel = _Channel([])
    r = await execute_task(
        Task("t", "这是一个很长的复杂任务目标需要拆分成多个子任务来处理",
             params={"a": 1, "b": 2}, risk="read"),
        s, CancellationToken(),
    )
    assert r["status"] == "done"
    assert "多智能体结果" in r["summary"]
    assert any(st["tool"] == "agent:doer" for st in r["steps"])


@pytest.mark.asyncio
async def test_execute_injects_context(monkeypatch):
    async def fake_build_context(query):
        return "【相关文档/环境】\nPython 3.14"

    monkeypatch.setattr("core.orchestrator.executor.build_context", fake_build_context)

    class _Fake:
        def __init__(self):
            self.msgs = None

        def retry_stream_chat(self, messages, tools=None):
            self.msgs = messages

            async def gen():
                yield _done(content="完成")
            return gen()

    fake = _Fake()
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)
    s = Session()
    s.channel = _Channel([])
    r = await execute_task(Task("t", "查 python 版本", risk="read"), s, CancellationToken())
    assert r["status"] == "done"
    assert "Python 3.14" in fake.msgs[0]["content"]


@pytest.mark.asyncio
async def test_execute_high_risk_confirm_rejected(monkeypatch):
    fake = _FakeLLM([
        [_done(tool="write_file", args=json.dumps({"path": "C:/x.txt", "content": "hi"}))],
        [_done(content="已跳过")],
    ])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)
    s = Session()
    s.channel = _Channel(["取消"])
    r = await execute_task(Task("t", "写文件", risk="write"), s, CancellationToken())
    assert r["status"] == "done"
    assert r["steps"][0]["status"] == "error"


@pytest.mark.asyncio
async def test_execute_emits_streaming_events(monkeypatch):
    import asyncio
    fake = _FakeLLM([
        [_done(tool="calculate", args=json.dumps({"expression": "1+1"})),
         {"type": "usage", "usage": {"total_tokens": 5}}],
        [{"type": "content_delta", "text": "结果是 "},
         {"type": "content_delta", "text": "2"},
         _done(content="结果是 2")],
    ])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)
    s = Session()
    s.channel = _Channel([])
    events: asyncio.Queue = asyncio.Queue()
    r = await execute_task(Task("t", "算 1+1", risk="read"), s, CancellationToken(), events)
    assert r["status"] == "done"
    evts = []
    while not events.empty():
        evts.append(events.get_nowait())
    types = [e["type"] for e in evts]
    assert "tool_start" in types and "tool_end" in types
    assert "usage" in types
    content = "".join(e.get("text", "") for e in evts if e["type"] == "content_delta")
    assert "结果是 2" in content
