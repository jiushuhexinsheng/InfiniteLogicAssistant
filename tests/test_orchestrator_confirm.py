# -*- coding: utf-8 -*-
import pytest

from core.orchestrator.confirm import confirm_if_needed, confirm_tool
from core.orchestrator.session import Session
from core.orchestrator.task import Task


class _Channel:
    def __init__(self, answers):
        self.answers = list(answers)
        self.notified: list[str] = []

    async def ask(self, q):
        return self.answers.pop(0)

    async def notify(self, text):
        self.notified.append(text)


@pytest.mark.asyncio
async def test_confirm_read_auto():
    s = Session()
    s.channel = _Channel([])
    assert await confirm_if_needed(Task("t", "读文件", risk="read"), "读 x", s) is True


@pytest.mark.asyncio
async def test_confirm_exec_yes():
    s = Session()
    s.channel = _Channel(["确认"])
    assert await confirm_if_needed(Task("t", "删文件", risk="exec"), "删除 x", s) is True
    assert "需要确认" in s.channel.notified[0]


@pytest.mark.asyncio
async def test_confirm_write_no():
    s = Session()
    s.channel = _Channel(["取消"])
    assert await confirm_if_needed(Task("t", "写文件", risk="write"), "覆盖 x", s) is False


@pytest.mark.asyncio
async def test_confirm_no_channel_rejects():
    s = Session()
    s.channel = None
    assert await confirm_if_needed(Task("t", "删文件", risk="exec"), "删除 x", s) is False


# ─── confirm_tool：基于工具实际风险（TOOLS.risk），不依赖任务声明的 risk ───

@pytest.mark.asyncio
async def test_confirm_tool_read_auto():
    s = Session()
    s.channel = _Channel([])
    assert await confirm_tool(s, "get_datetime", {}) is True


@pytest.mark.asyncio
async def test_confirm_tool_write_yes():
    s = Session()
    s.channel = _Channel(["确认"])
    assert await confirm_tool(s, "write_file", {"path": "x", "content": "y"}) is True
    assert "需要确认" in s.channel.notified[0]


@pytest.mark.asyncio
async def test_confirm_tool_write_no():
    s = Session()
    s.channel = _Channel(["取消"])
    assert await confirm_tool(s, "write_file", {"path": "x", "content": "y"}) is False


@pytest.mark.asyncio
async def test_confirm_tool_no_channel_rejects():
    s = Session()
    s.channel = None
    assert await confirm_tool(s, "write_file", {"path": "x", "content": "y"}) is False
