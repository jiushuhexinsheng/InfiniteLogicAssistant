# -*- coding: utf-8 -*-
import json

import pytest

from core.orchestrator.clarify import run_clarify
from core.orchestrator.intent import IntentResult
from core.orchestrator.session import Session
from core.orchestrator.task import Task, form_task


def _done_with_form(goal, params, missing, risk) -> dict:
    return {
        "type": "done",
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "f", "type": "function",
                "function": {"name": "form_task",
                             "arguments": json.dumps({"goal": goal, "params": params, "missing": missing, "risk": risk})},
            }],
        },
    }


class _FakeLLM:
    def __init__(self, script):
        self.script = script

    def retry_stream_chat(self, messages, tools=None):
        async def gen():
            for evt in self.script.pop(0):
                yield evt
        return gen()


@pytest.mark.asyncio
async def test_form_task(monkeypatch):
    fake = _FakeLLM([[_done_with_form("复制文件", {"src": "桌面readme.txt"}, ["复制到哪里？"], "write")]])
    monkeypatch.setattr("core.orchestrator.task.get_llm_client", lambda: fake)
    t = await form_task(IntentResult(type="task", summary="把桌面readme.txt复制到下载"))
    assert t.goal == "复制文件"
    assert t.params == {"src": "桌面readme.txt"}
    assert t.missing == ["复制到哪里？"]
    assert t.risk == "write"
    assert t.id


@pytest.mark.asyncio
async def test_run_clarify_asks_operator(monkeypatch):
    class _Channel:
        def __init__(self, answers):
            self.answers = list(answers)
            self.asked: list[str] = []

        async def ask(self, q):
            self.asked.append(q)
            return self.answers.pop(0)

        async def notify(self, text):
            pass

    script = [
        Task("t", "复制文件", {"src": "桌面readme.txt"}, ["目标位置？"], "write"),
        Task("t", "复制文件", {"src": "桌面readme.txt", "dest": "下载"}, [], "write"),
    ]
    calls = {"n": 0}

    async def fake_form(intent):
        # script[0] 是初始任务，澄清内部的首次 form_task 应返回已解析的 script[1]
        t = script[min(calls["n"] + 1, len(script) - 1)]
        calls["n"] += 1
        return t

    monkeypatch.setattr("core.orchestrator.clarify.form_task", fake_form)

    s = Session()
    s.channel = _Channel(["下载"])
    task = script[0]
    params = await run_clarify(s, task)
    assert s.channel.asked == ["目标位置？"]
    assert params == {"src": "桌面readme.txt", "dest": "下载"}
