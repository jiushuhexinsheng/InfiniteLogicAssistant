# -*- coding: utf-8 -*-
"""定时任务无人值守执行 — 被拒通知与结果落盘。
Scheduled unattended task execution — rejected confirmations and result persistence.
"""
import pytest

from core.orchestrator.session import Answer
from core.scheduler.runner import _SilentChannel


@pytest.mark.asyncio
async def test_silent_channel_ask_records_rejected():
    """测试静默通道在无人应答时记录被拒请求。Tests the silent channel recording rejected asks when no one answers."""
    ch = _SilentChannel()
    ans = await ch.ask("确认执行吗？删除 /tmp/x", kind="choice",
                       options=[{"value": "yes", "label": "确认"}, {"value": "no", "label": "取消"}])
    assert ans == Answer()  # 无人应答 → 无 choice → 确认被拒
    assert ans.choice is None
    assert ch.rejected == ["确认执行吗？删除 /tmp/x"]


@pytest.mark.asyncio
async def test_run_scheduled_cancelled_persists_and_returns_rejected(monkeypatch):
    """测试确认被拒时任务以 cancelled 结束、会话落盘并返回被拒列表。Tests a task ending cancelled with persisted session and returned rejections."""
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
    """测试只读任务以 done 结束且无被拒确认。Tests a read-only task ending with done status and no rejections."""
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
