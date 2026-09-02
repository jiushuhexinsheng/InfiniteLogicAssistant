# -*- coding: utf-8 -*-
"""确认流程（confirm_if_needed / confirm_tool / 否定答案识别）的测试。
Tests for the confirmation flow (confirm_if_needed / confirm_tool / negative answer detection).
"""
import pytest

from core.orchestrator.confirm import confirm_if_needed, confirm_tool
from core.orchestrator.session import Session
from core.orchestrator.task import Task


class _Channel:
    """模拟会话通道，返回预设答案并记录通知。Simulates a session channel with preset answers and recorded notifications."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.notified: list[str] = []

    async def ask(self, q):
        return self.answers.pop(0)

    async def notify(self, text):
        self.notified.append(text)


@pytest.mark.asyncio
async def test_confirm_read_auto():
    """读操作自动放行。Read operations auto-approve."""
    s = Session()
    s.channel = _Channel([])
    assert await confirm_if_needed(Task("t", "读文件", risk="read"), "读 x", s) is True


@pytest.mark.asyncio
async def test_confirm_exec_yes():
    """高风险操作回答确认后放行。A confirmed answer approves a high-risk operation."""
    s = Session()
    s.channel = _Channel(["确认"])
    assert await confirm_if_needed(Task("t", "删文件", risk="exec"), "删除 x", s) is True
    assert "需要确认" in s.channel.notified[0]


@pytest.mark.asyncio
async def test_confirm_write_no():
    """高风险操作回答取消后被拒绝。A cancel answer rejects a high-risk operation."""
    s = Session()
    s.channel = _Channel(["取消"])
    assert await confirm_if_needed(Task("t", "写文件", risk="write"), "覆盖 x", s) is False


@pytest.mark.asyncio
async def test_confirm_no_channel_rejects():
    """无会话通道时默认拒绝。Defaults to rejection when no channel is present."""
    s = Session()
    s.channel = None
    assert await confirm_if_needed(Task("t", "删文件", risk="exec"), "删除 x", s) is False


# ─── _classify_answer：否定感知判定（不是/不执行/不可以 不得误判为同意）───

from core.orchestrator.confirm import _classify_answer


@pytest.mark.parametrize(
    "ans",
    [
        "不是",
        "不执行",
        "不可以",
        "不同意",
        "别执行",
        "不要",
        "取消",
        "拒绝",
        "不行",
        "停下",
    ],
)
def test_classify_negative(ans):
    """否定回答全部判定为拒绝。All negative answers classify as rejected."""
    assert _classify_answer(ans) is False


@pytest.mark.parametrize(
    "ans",
    ["确认", "执行吧", "可以", "是的", "同意", "确定", "好", "嗯，执行", "没错，执行"],
)
def test_classify_positive(ans):
    """肯定回答全部判定为同意。All affirmative answers classify as approved."""
    assert _classify_answer(ans) is True


@pytest.mark.parametrize("ans", ["", "   ", "随便", "听你的", "再想想"])
def test_classify_ambiguous(ans):
    """模糊回答判定为需要澄清。Ambiguous answers classify as needing clarification."""
    assert _classify_answer(ans) is None


@pytest.mark.asyncio
async def test_confirm_negated_answer_rejected():
    """否定回答不误判为同意。A negated answer is not misread as approval."""
    s = Session()
    s.channel = _Channel(["不是"])
    assert await confirm_if_needed(Task("t", "删文件", risk="exec"), "删除 x", s) is False


@pytest.mark.asyncio
async def test_confirm_negated_tool_rejected():
    """否定回答导致工具确认被拒。A negated answer rejects the tool confirmation."""
    s = Session()
    s.channel = _Channel(["不执行"])
    assert await confirm_tool(s, "write_file", {"path": "x", "content": "y"}) is False


# ─── confirm_tool：基于工具实际风险（TOOLS.risk），不依赖任务声明的 risk ───

@pytest.mark.asyncio
async def test_confirm_tool_read_auto():
    """低风险工具自动放行。Low-risk tools auto-approve."""
    s = Session()
    s.channel = _Channel([])
    assert await confirm_tool(s, "get_datetime", {}) is True


@pytest.mark.asyncio
async def test_confirm_tool_write_yes():
    """高风险工具回答确认后放行。A confirmed answer approves a high-risk tool."""
    s = Session()
    s.channel = _Channel(["确认"])
    assert await confirm_tool(s, "write_file", {"path": "x", "content": "y"}) is True
    assert "需要确认" in s.channel.notified[0]


@pytest.mark.asyncio
async def test_confirm_tool_write_no():
    """高风险工具回答取消后被拒。A cancel answer rejects a high-risk tool."""
    s = Session()
    s.channel = _Channel(["取消"])
    assert await confirm_tool(s, "write_file", {"path": "x", "content": "y"}) is False


@pytest.mark.asyncio
async def test_confirm_tool_no_channel_rejects():
    """无通道时工具确认默认拒绝。Tool confirmation defaults to rejection without a channel."""
    s = Session()
    s.channel = None
    assert await confirm_tool(s, "write_file", {"path": "x", "content": "y"}) is False
