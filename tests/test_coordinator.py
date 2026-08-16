# -*- coding: utf-8 -*-
from types import SimpleNamespace

import pytest

from core.agent.coordinator import run_coordinator
from core.orchestrator.control import CancellationToken
from core.orchestrator.session import Session
from core.orchestrator.task import Task


@pytest.mark.asyncio
async def test_coordinator_merges_subtasks(monkeypatch):
    async def fake_decompose(task):
        return [
            {"goal": "子任务1", "agent_type": "doer", "independent": True},
            {"goal": "子任务2", "agent_type": "searcher", "independent": True},
        ]

    async def fake_subagent(role, goal, context="", cancel=None, max_steps=None):
        return SimpleNamespace(status="done", output=f"结果:{goal}", used_tools=["get_datetime"])

    monkeypatch.setattr("core.agent.coordinator._decompose", fake_decompose)
    monkeypatch.setattr("core.agent.coordinator.run_subagent", fake_subagent)

    s = Session()
    r = await run_coordinator(Task("t", "主任务"), s, CancellationToken())
    assert r["status"] == "done"
    assert len(r["subtasks"]) == 2
    assert any("子任务1" in x["goal"] for x in r["subtasks"])


@pytest.mark.asyncio
async def test_coordinator_emits_notify_events(monkeypatch):
    async def fake_decompose(task):
        return [{"goal": "子任务", "agent_type": "doer", "independent": False}]

    async def fake_subagent(role, goal, context="", cancel=None, max_steps=None):
        return SimpleNamespace(status="done", output="完成", used_tools=[])

    monkeypatch.setattr("core.agent.coordinator._decompose", fake_decompose)
    monkeypatch.setattr("core.agent.coordinator.run_subagent", fake_subagent)

    events = []

    class _Rec:
        async def notify(self, text):
            events.append(text)
        async def ask(self, q):
            return ""

    s = Session()
    s.channel = _Rec()
    r = await run_coordinator(Task("t", "主任务"), s, CancellationToken())
    assert r["status"] == "done"
    assert any("已拆分" in e for e in events)
    assert any("子代理 doer 开始" in e for e in events)
    assert any("子代理 doer 完成" in e for e in events)
    assert any("批评" in e for e in events)


@pytest.mark.asyncio
async def test_coordinator_cancelled_before(monkeypatch):
    token = CancellationToken()
    token.cancel()
    s = Session()
    r = await run_coordinator(Task("t", "主任务"), s, token)
    assert r["status"] == "stopped"
    assert r["subtasks"] == []
