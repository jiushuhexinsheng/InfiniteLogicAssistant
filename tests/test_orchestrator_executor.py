# -*- coding: utf-8 -*-
"""执行器（execute_task）各路径的测试。
Tests for the executor (execute_task) covering its main paths.
"""
import json

import pytest

from core.orchestrator.control import CancellationToken
from core.orchestrator.executor import execute_task
from core.orchestrator.session import Answer, Session
from core.orchestrator.task import Task


def _done(content=None, tool=None, args="{}"):
    msg = {"role": "assistant", "content": content or ""}
    if tool:
        msg["tool_calls"] = [{"id": "c", "type": "function", "function": {"name": tool, "arguments": args}}]
    return {"type": "done", "message": msg}


class _FakeLLM:
    """模拟 LLM 客户端，按脚本逐轮回放事件。Simulates an LLM client that replays scripted events turn by turn."""

    def __init__(self, script):
        self.script = script

    def retry_stream_chat(self, messages, tools=None):
        async def gen():
            for evt in self.script.pop(0):
                yield evt
        return gen()


class _Channel:
    """模拟会话通道，返回预设答案。Simulates a session channel returning preset answers."""

    def __init__(self, answers):
        self.answers = list(answers)

    async def ask(self, q, *, kind="text", options=None):
        a = self.answers.pop(0)
        return a if isinstance(a, Answer) else Answer(text=a)

    async def notify(self, text):
        pass


@pytest.mark.asyncio
async def test_execute_converges(monkeypatch):
    """工具调用后收敛到 done。Converges to done after a tool call."""
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
    """达到步数上限后失败。Fails after hitting the step limit."""
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
    """执行前已取消则返回 stopped。Returns stopped when cancelled before execution."""
    token = CancellationToken()
    token.cancel()
    s = Session()
    s.channel = _Channel([])
    r = await execute_task(Task("t", "x", risk="read"), s, token)
    assert r["status"] == "stopped"


@pytest.mark.asyncio
async def test_execute_uses_coordinator_for_complex(monkeypatch):
    """复杂任务交给多智能体协调器。Complex tasks are delegated to the multi-agent coordinator."""
    from core import config as config_mod

    async def fake_coordinator(task, session, cancel, events=None):
        return {"status": "done", "summary": "多智能体结果", "subtasks": [
            {"goal": "a", "agent_type": "doer", "status": "done", "output": "ok", "tools": []}]}

    monkeypatch.setattr("core.orchestrator.executor.run_coordinator", fake_coordinator)
    monkeypatch.setattr(config_mod, "get_settings",
                        lambda: config_mod.Settings(agent=config_mod.AgentSection(multi_agent=True)))
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
    """上下文注入到首条用户消息。Context is injected into the first user message."""
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
async def test_execute_multi_agent_streams_summary_and_records(monkeypatch):
    """多智能体摘要流式输出并记录到会话。The multi-agent summary streams out and is recorded in the session."""
    import asyncio
    from core import config as config_mod

    async def fake_coordinator(task, session, cancel, events=None):
        return {"status": "done", "summary": "多智能体最终结论：已全部完成", "subtasks": [
            {"goal": "a", "agent_type": "doer", "status": "done", "output": "ok", "tools": []}]}

    monkeypatch.setattr("core.orchestrator.executor.run_coordinator", fake_coordinator)
    monkeypatch.setattr(config_mod, "get_settings",
                        lambda: config_mod.Settings(agent=config_mod.AgentSection(multi_agent=True)))
    s = Session()
    s.channel = _Channel([])
    events: asyncio.Queue = asyncio.Queue()
    r = await execute_task(
        Task("t", "这是一个很长的复杂任务目标需要拆分成多个子任务来处理",
             params={"a": 1, "b": 2}, risk="read"),
        s, CancellationToken(), events,
    )
    assert r["status"] == "done"
    deltas = "".join(e.get("text", "") for e in _drain(events) if e["type"] == "content_delta")
    assert deltas == "多智能体最终结论：已全部完成"
    assert any(m.get("role") == "assistant" and "多智能体最终结论" in m.get("content", "") for m in s.messages)


@pytest.mark.asyncio
async def test_execute_records_assistant_reply(monkeypatch):
    """助手回复记录进会话历史。The assistant reply is recorded in the session history."""
    fake = _FakeLLM([
        [_done(content="结果是 2")],
    ])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)
    s = Session()
    s.channel = _Channel([])
    r = await execute_task(Task("t", "算 1+1", risk="read"), s, CancellationToken())
    assert r["status"] == "done"
    assert any(m.get("role") == "assistant" and "结果是 2" in m.get("content", "") for m in s.messages)


def _drain(q):
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


@pytest.mark.asyncio
async def test_execute_read_tools_run_concurrently(monkeypatch):
    """read 级工具并发执行且按序回喂。Read-level tools run concurrently and feed back in order."""
    msg = {
        "role": "assistant", "content": "",
        "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "calculate", "arguments": json.dumps({"expression": "1+1"})}},
            {"id": "c2", "type": "function", "function": {"name": "get_datetime", "arguments": "{}"}},
        ],
    }
    fake = _FakeLLM([
        [{"type": "done", "message": msg}],
        [_done(content="完成")],
    ])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)
    s = Session()
    s.channel = _Channel([])
    r = await execute_task(Task("t", "多工具", risk="read"), s, CancellationToken())
    assert r["status"] == "done"
    # read 级工具并发执行，结果按原顺序回喂
    tools = [st["tool"] for st in r["steps"]]
    assert tools == ["calculate", "get_datetime"]
    assert all(st["status"] == "ok" for st in r["steps"])


@pytest.mark.asyncio
async def test_execute_high_risk_confirm_rejected(monkeypatch):
    """高风险工具经操作者取消后记为错误。A high-risk tool cancelled by the operator is recorded as an error."""
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
async def test_execute_high_risk_tool_confirm_ignores_task_risk_read(monkeypatch):
    """任务误标 read 时仍按工具实际风险确认。Tool risk still gates confirmation even when the task is mislabeled as read."""
    # 堵洞：任务被 LLM 误标为 read，但调用了 write_file → 仍必须经操作者确认（答「取消」被拒）
    fake = _FakeLLM([
        [_done(tool="write_file", args=json.dumps({"path": "C:/x.txt", "content": "hi"}))],
        [_done(content="已跳过")],
    ])
    monkeypatch.setattr("core.orchestrator.executor.get_llm_client", lambda: fake)
    s = Session()
    s.channel = _Channel(["取消"])
    r = await execute_task(Task("t", "写文件", risk="read"), s, CancellationToken())
    assert r["status"] == "done"
    assert r["steps"][0]["status"] == "error"


@pytest.mark.asyncio
async def test_execute_emits_streaming_events(monkeypatch):
    """执行过程发出流式事件。Execution emits streaming events."""
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
