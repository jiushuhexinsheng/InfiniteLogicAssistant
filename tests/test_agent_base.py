# -*- coding: utf-8 -*-
"""该模块测试 core.agent.base 中子代理运行的核心行为：收敛到 done 状态、取消、工具事件，以及高风险工具的确认机制。
Tests the core behaviors of subagent execution in core.agent.base: convergence to done, cancellation, tool events, and the confirmation mechanism for high-risk tools.
"""
import json

import pytest

from core.agent.base import run_subagent
from core.orchestrator.control import CancellationToken


def _done(content=None, tool=None, args="{}"):
    msg = {"role": "assistant", "content": content or ""}
    if tool:
        msg["tool_calls"] = [{"id": "c", "type": "function", "function": {"name": tool, "arguments": args}}]
    return {"type": "done", "message": msg}


class _FakeLLM:
    """按脚本回放事件流的假 LLM 客户端，用于测试子代理运行。
    A fake LLM client that replays event streams from a script, used for testing subagent runs.
    """
    def __init__(self, script):
        self.script = script

    def retry_stream_chat(self, messages, tools=None):
        async def gen():
            for evt in self.script.pop(0):
                yield evt
        return gen()


@pytest.mark.asyncio
async def test_subagent_converges(monkeypatch):
    """验证子代理在工具调用后收敛到 done 状态。Verifies the subagent converges to the done state after a tool call."""
    fake = _FakeLLM([
        [_done(tool="get_datetime")],
        [_done(content="完成了")],
    ])
    monkeypatch.setattr("core.agent.base.get_llm_client", lambda: fake)
    r = await run_subagent("你是助手", "查时间")
    assert r.status == "done"
    assert "完成了" in r.output
    assert "get_datetime" in r.used_tools


@pytest.mark.asyncio
async def test_subagent_cancelled(monkeypatch):
    """验证取消令牌生效时子代理停止并返回 stopped 状态。Verifies the subagent stops with the stopped status when the cancellation token is triggered."""
    token = CancellationToken()
    token.cancel()
    r = await run_subagent("你是助手", "x", cancel=token)
    assert r.status == "stopped"


@pytest.mark.asyncio
async def test_subagent_emits_tool_events(monkeypatch):
    """验证子代理运行期间发出工具开始与结束事件。Verifies the subagent emits tool start and end events during its run."""
    import asyncio
    fake = _FakeLLM([
        [_done(tool="get_datetime")],
        [_done(content="完成")],
    ])
    monkeypatch.setattr("core.agent.base.get_llm_client", lambda: fake)
    events: asyncio.Queue = asyncio.Queue()
    r = await run_subagent("你是助手", "查时间", events=events)
    assert r.status == "done"
    evts = []
    while not events.empty():
        evts.append(events.get_nowait())
    assert any(e["type"] == "tool_start" and e["name"] == "get_datetime" for e in evts)
    assert any(e["type"] == "tool_end" and e["name"] == "get_datetime" and e["status"] == "ok" for e in evts)


# ─── 子代理高风险工具确认：非 read 工具未经确认不得执行 ───

def _spy_acall(monkeypatch):
    """替换 TOOLS.acall 为 spy，返回 ok 且记录调用；不真正执行任何工具。
    Replaces TOOLS.acall with a spy that returns ok and records calls without actually executing any tool.
    """
    calls = []

    async def fake_acall(name, args, cancel=None):
        calls.append(name)
        return "ok"
    monkeypatch.setattr("core.agent.base.TOOLS.acall", fake_acall)
    return calls


@pytest.mark.asyncio
async def test_subagent_high_risk_tool_rejected_without_confirm(monkeypatch):
    """验证无确认通道时高风险工具未经确认不会执行。Verifies a high-risk tool is not executed without confirmation when no confirm channel is provided."""
    fake = _FakeLLM([
        [_done(tool="write_file", args=json.dumps({"path": "C:/x.txt", "content": "hi"}))],
        [_done(content="完成")],
    ])
    monkeypatch.setattr("core.agent.base.get_llm_client", lambda: fake)
    calls = _spy_acall(monkeypatch)
    r = await run_subagent("你是助手", "写文件")
    assert r.status == "done"
    assert calls == []  # 无确认通道 → 非 read 工具未实际执行


@pytest.mark.asyncio
async def test_subagent_high_risk_tool_confirm_rejected(monkeypatch):
    """验证操作者拒绝确认时高风险工具不会执行。Verifies a high-risk tool is not executed when the operator rejects confirmation."""
    fake = _FakeLLM([
        [_done(tool="write_file", args=json.dumps({"path": "C:/x.txt", "content": "hi"}))],
        [_done(content="完成")],
    ])
    monkeypatch.setattr("core.agent.base.get_llm_client", lambda: fake)
    calls = _spy_acall(monkeypatch)

    async def confirm(name, args):
        return False
    r = await run_subagent("你是助手", "写文件", confirm=confirm)
    assert r.status == "done"
    assert calls == []  # 操作者拒绝 → 工具未执行


@pytest.mark.asyncio
async def test_subagent_high_risk_tool_confirm_approved(monkeypatch):
    """验证操作者批准确认后高风险工具会被执行。Verifies a high-risk tool is executed after the operator approves confirmation."""
    fake = _FakeLLM([
        [_done(tool="write_file", args=json.dumps({"path": "C:/x.txt", "content": "hi"}))],
        [_done(content="完成")],
    ])
    monkeypatch.setattr("core.agent.base.get_llm_client", lambda: fake)
    calls = _spy_acall(monkeypatch)

    async def confirm(name, args):
        return True
    r = await run_subagent("你是助手", "写文件", confirm=confirm)
    assert r.status == "done"
    assert calls == ["write_file"]  # 确认后执行
