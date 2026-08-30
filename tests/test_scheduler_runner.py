# -*- coding: utf-8 -*-
"""定时任务无人值守执行 — 被拒通知与结果落盘"""
import pytest

from core.scheduler.runner import _SilentChannel


@pytest.mark.asyncio
async def test_silent_channel_ask_records_rejected():
    ch = _SilentChannel()
    ans = await ch.ask("确认执行吗？删除 /tmp/x")
    assert ans == ""  # 无人应答 → 拒绝
    assert ch.rejected == ["确认执行吗？删除 /tmp/x"]


@pytest.mark.asyncio
async def test_run_scheduled_cancelled_persists_and_returns_rejected(monkeypatch):
    from core.scheduler.runner import run_scheduled
    captured = {}

    async def fake_persist(session, created=None):
        captured["session"] = session

    async def fake_pipeline(text, session, events, controller, channel=None, messages=None):
        # 模拟：高风险任务，无人应答 → 确认被拒
        await channel.ask("确认执行吗？删除 /tmp/x")
        session.append("assistant", "操作者未确认，任务取消")
        await events.put({"type": "task_state", "state": "done", "status": "cancelled",
                          "summary": "操作者未确认，任务取消"})
        await events.put({"type": "done"})

    monkeypatch.setattr("core.api.state.persist", fake_persist)
    monkeypatch.setattr("core.scheduler.runner.run_pipeline", fake_pipeline)

    result = await run_scheduled("定时删除 /tmp/x")

    assert result["status"] == "cancelled"
    assert result["summary"] == "操作者未确认，任务取消"
    assert result["rejected"] == ["确认执行吗？删除 /tmp/x"]
    assert captured["session"] is not None  # 会话已落盘（控制台可见）


@pytest.mark.asyncio
async def test_run_scheduled_readonly_returns_done(monkeypatch):
    from core.scheduler.runner import run_scheduled
    captured = {}

    async def fake_persist(session, created=None):
        captured["session"] = session

    async def fake_pipeline(text, session, events, controller, channel=None, messages=None):
        session.append("assistant", "查询完成")
        await events.put({"type": "task_state", "state": "done", "status": "done", "summary": "查询完成"})
        await events.put({"type": "done"})

    monkeypatch.setattr("core.api.state.persist", fake_persist)
    monkeypatch.setattr("core.scheduler.runner.run_pipeline", fake_pipeline)

    result = await run_scheduled("查询天气")

    assert result["status"] == "done"
    assert result["rejected"] == []  # 只读任务无被拒确认
    assert captured["session"] is not None
