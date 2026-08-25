# -*- coding: utf-8 -*-
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
    def __init__(self, script):
        self.script = script

    def retry_stream_chat(self, messages, tools=None):
        async def gen():
            for evt in self.script.pop(0):
                yield evt
        return gen()


@pytest.mark.asyncio
async def test_subagent_converges(monkeypatch):
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
    token = CancellationToken()
    token.cancel()
    r = await run_subagent("你是助手", "x", cancel=token)
    assert r.status == "stopped"


# ─── 子代理高风险工具确认：非 read 工具未经确认不得执行 ───

def _spy_acall(monkeypatch):
    """替换 TOOLS.acall 为 spy，返回 ok 且记录调用；不真正执行任何工具。"""
    calls = []

    async def fake_acall(name, args):
        calls.append(name)
        return "ok"
    monkeypatch.setattr("core.agent.base.TOOLS.acall", fake_acall)
    return calls


@pytest.mark.asyncio
async def test_subagent_high_risk_tool_rejected_without_confirm(monkeypatch):
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
