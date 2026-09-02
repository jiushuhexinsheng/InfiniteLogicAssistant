# -*- coding: utf-8 -*-
"""定时任务调度器（core.scheduler.scheduler）的测试。
Tests for the scheduled task scheduler (core.scheduler.scheduler).
"""
from datetime import datetime

import pytest

from core.scheduler.scheduler import Scheduler, _match, cron_matches


def test_cron_matches():
    """测试 cron 表达式是否匹配给定时间。Tests whether a cron expression matches a given time."""
    assert cron_matches("* * * * *", datetime(2026, 8, 13, 10, 30))
    assert cron_matches("30 10 * * *", datetime(2026, 8, 13, 10, 30))
    assert not cron_matches("0 9 * * *", datetime(2026, 8, 13, 10, 30))
    assert not cron_matches("bad", datetime(2026, 8, 13, 10, 30))


def test_cron_step_list_range():
    """测试 cron 的步长、列表与范围语法。Tests cron step, list and range syntax."""
    # 步长：*/n
    assert cron_matches("*/15 * * * *", datetime(2026, 8, 13, 10, 15))
    assert not cron_matches("*/15 * * * *", datetime(2026, 8, 13, 10, 14))
    # 列表：a,b,c
    assert cron_matches("0,30 9 * * *", datetime(2026, 8, 13, 9, 30))
    assert not cron_matches("0,30 9 * * *", datetime(2026, 8, 13, 9, 15))
    # 范围：a-b
    assert cron_matches("0 9-18 * * *", datetime(2026, 8, 13, 14, 0))
    assert not cron_matches("0 9-18 * * *", datetime(2026, 8, 13, 8, 0))
    # 带步长的范围：a-b/n
    assert cron_matches("0 8-18/2 * * *", datetime(2026, 8, 13, 12, 0))
    assert not cron_matches("0 8-18/2 * * *", datetime(2026, 8, 13, 11, 0))


def test_cron_field_match_dow_and_invalid():
    """测试字段匹配的星期语义与非法表达式处理。Tests field matching for day-of-week semantics and invalid expressions."""
    # 星期字段（0/7=周日，1-5=周一至周五）
    assert _match("1-5", 3) is True
    assert _match("1-5", 0) is False
    assert _match("0,6", 0) is True
    assert _match("*/2", 4) is True
    assert _match("*/2", 3) is False
    assert _match("1-10/3", 7) is True
    assert _match("1-10/3", 8) is False
    assert _match("", 1) is False
    assert _match("0/0", 5) is False  # 非法步长


def test_scheduler_add_list_remove(tmp_path):
    """测试任务的新增、列出与删除。Tests adding, listing and removing scheduled tasks."""
    s = Scheduler(path=tmp_path / "s.json")
    sc = s.add("0 9 * * *", "查天气")
    assert s.all() and s.all()[0].id == sc.id
    s.remove(sc.id)
    assert not s.all()


@pytest.mark.asyncio
async def test_scheduler_check_fire_dedup(tmp_path):
    """测试同一分钟内任务不会重复触发。Tests that a task is not fired twice within the same minute."""
    fired: list[str] = []

    async def on_fire(prompt):
        fired.append(prompt)

    s = Scheduler(path=tmp_path / "s.json", on_fire=on_fire)
    s.add("30 10 * * *", "任务X")
    fired_ids = s._check_and_fire(datetime(2026, 8, 13, 10, 30))
    assert fired_ids
    # 同一分钟不重复触发
    assert s._check_and_fire(datetime(2026, 8, 13, 10, 30)) == []


def test_scheduler_persists(tmp_path):
    """测试任务持久化后重新加载仍然存在。Tests that tasks persist and remain after reloading."""
    s = Scheduler(path=tmp_path / "s.json")
    sc = s.add("0 9 * * *", "持久化任务")
    s2 = Scheduler(path=tmp_path / "s.json")
    assert any(x.id == sc.id for x in s2.all())


@pytest.mark.asyncio
async def test_run_scheduled_uses_silent_channel(monkeypatch):
    """测试定时运行使用静默通道。Tests that scheduled runs use the silent channel."""
    from core.scheduler.runner import run_scheduled
    captured = {}

    async def fake_pipeline(text, session, events, controller, channel=None):
        captured["channel"] = channel

    monkeypatch.setattr("core.scheduler.runner.run_pipeline", fake_pipeline)
    await run_scheduled("查天气")
    assert captured["channel"] is not None
