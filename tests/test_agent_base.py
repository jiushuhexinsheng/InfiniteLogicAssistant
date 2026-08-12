# -*- coding: utf-8 -*-
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
