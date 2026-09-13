# -*- coding: utf-8 -*-
"""确认流程（confirm_if_needed / confirm_tool / 结构化确认）的测试。
Tests for the confirmation flow (confirm_if_needed / confirm_tool / structured confirmation).
"""
import pytest

from core.orchestrator.confirm import _resolve_confirm, confirm_if_needed, confirm_tool
from core.orchestrator.session import Answer, Session
from core.orchestrator.task import Task


class _Channel:
    """模拟会话通道：返回预设答案（Answer 或字符串）并记录通知、提问类型与选项。
    Simulates a session channel: returns preset answers (Answer or str), recording notifications, question kinds and options.
    """

    def __init__(self, answers):
        self.answers = list(answers)
        self.notified: list[str] = []
        self.kinds: list[str] = []
        self.options: list[list] = []

    async def ask(self, q, *, kind="text", options=None):
        self.kinds.append(kind)
        self.options.append(options or [])
        a = self.answers.pop(0)
        return a if isinstance(a, Answer) else Answer(text=a)

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
    """高风险操作点击「确认」后放行。Clicking "confirm" approves a high-risk operation."""
    s = Session()
    s.channel = _Channel([Answer(choice="yes")])
    assert await confirm_if_needed(Task("t", "删文件", risk="exec"), "删除 x", s) is True
    assert "需要确认" in s.channel.notified[0]


@pytest.mark.asyncio
async def test_confirm_write_no():
    """高风险操作点击「取消」后被拒绝。Clicking "cancel" rejects a high-risk operation."""
    s = Session()
    s.channel = _Channel([Answer(choice="no")])
    assert await confirm_if_needed(Task("t", "写文件", risk="write"), "覆盖 x", s) is False


@pytest.mark.asyncio
async def test_confirm_no_channel_rejects():
    """无会话通道时默认拒绝。Defaults to rejection when no channel is present."""
    s = Session()
    s.channel = None
    assert await confirm_if_needed(Task("t", "删文件", risk="exec"), "删除 x", s) is False


@pytest.mark.asyncio
async def test_confirm_asks_as_choice_with_two_options():
    """确认提问必须是 kind="choice" 且恰带「允许本次 / 拒绝」两个选项。
    A confirmation question must be kind="choice" with exactly the allow-once / deny options."""
    s = Session()
    s.channel = _Channel([Answer(choice="yes")])
    await confirm_if_needed(Task("t", "删文件", risk="exec"), "删除 x", s)
    assert s.channel.kinds == ["choice"]
    assert s.channel.options[0] == [
        {"value": "yes", "label": "允许本次"},
        {"value": "no", "label": "拒绝"},
    ]


@pytest.mark.asyncio
async def test_confirm_tool_asks_as_choice():
    """工具级确认同样是选择类。Tool-level confirmation is a choice question too."""
    s = Session()
    s.channel = _Channel([Answer(choice="no")])
    await confirm_tool(s, "write_file", {"path": "x", "content": "y"})
    assert s.channel.kinds == ["choice"]
    assert [o["value"] for o in s.channel.options[0]] == ["yes", "no"]


# ─── _resolve_confirm：结构化选择优先，自由文本只认精确匹配 ───


@pytest.mark.parametrize("choice", ["yes"])
def test_resolve_structured_approve(choice):
    """结构化 choice=yes 判定为同意。Structured choice=yes classifies as approved."""
    assert _resolve_confirm(Answer(choice=choice)) is True


@pytest.mark.parametrize("choice", ["no"])
def test_resolve_structured_reject(choice):
    """结构化 choice=no 判定为拒绝。Structured choice=no classifies as rejected."""
    assert _resolve_confirm(Answer(choice=choice)) is False


@pytest.mark.parametrize("choice", ["maybe", "YES", "", "取消"])
def test_resolve_unknown_choice_rejects(choice):
    """无法识别的 choice 一律拒绝（fail closed）。An unrecognized choice is rejected (fail closed)."""
    assert _resolve_confirm(Answer(choice=choice)) is False


@pytest.mark.parametrize("text", ["确认", "确认 ", " 确认", "yes", "approve"])
def test_resolve_exact_text_approve(text):
    """无 choice 时，精确等于同义词表才放行。Without a choice, only an exact match against the synonym list approves."""
    assert _resolve_confirm(Answer(text=text)) is True


@pytest.mark.parametrize(
    "text",
    [
        # 否定语义：绝不能因为含「执行/是/可以」等子串而放行
        "不要执行", "不执行", "不是", "不可以", "不同意", "别执行", "取消", "拒绝", "不行", "停下", "no", "reject",
        # 犹豫句式：第四轮压测出的误放行，现应全部拒绝
        "不太确定", "我不想执行", "这个不太好吧", "等我确认一下", "我先确认一下再执行",
        # 非精确的肯定表达：结构化确认已由按钮承担，自由文本不再做子串猜测
        "嗯，执行", "没错，执行", "执行吧", "好的", "可以", "是",
        # 空 / 模糊
        "", "   ", "随便", "听你的", "再想想",
    ],
)
def test_resolve_text_rejects_unless_exact(text):
    """除精确匹配外，一切自由文本判定为拒绝。Everything except an exact match is rejected."""
    assert _resolve_confirm(Answer(text=text)) is False


@pytest.mark.asyncio
async def test_confirm_negated_answer_rejected():
    """否定回答不误判为同意。A negated answer is not misread as approval."""
    s = Session()
    s.channel = _Channel(["不是"])
    assert await confirm_if_needed(Task("t", "删文件", risk="exec"), "删除 x", s) is False


@pytest.mark.asyncio
async def test_confirm_hesitant_answer_rejected():
    """犹豫回答不误判为同意（旧关键词子串匹配会放行）。A hesitant answer is not misread as approval (the old substring matcher approved these)."""
    for hesitant in ("不太确定", "我不想执行", "这个不太好吧"):
        s = Session()
        s.channel = _Channel([hesitant])
        assert await confirm_if_needed(Task("t", "删文件", risk="exec"), "删除 x", s) is False, hesitant


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
    """高风险工具点击「确认」后放行。Clicking "confirm" approves a high-risk tool."""
    s = Session()
    s.channel = _Channel([Answer(choice="yes")])
    assert await confirm_tool(s, "write_file", {"path": "x", "content": "y"}) is True
    assert "需要确认" in s.channel.notified[0]


@pytest.mark.asyncio
async def test_confirm_tool_write_no():
    """高风险工具点击「取消」后被拒。Clicking "cancel" rejects a high-risk tool."""
    s = Session()
    s.channel = _Channel([Answer(choice="no")])
    assert await confirm_tool(s, "write_file", {"path": "x", "content": "y"}) is False


@pytest.mark.asyncio
async def test_confirm_tool_no_channel_rejects():
    """无通道时工具确认默认拒绝。Tool confirmation defaults to rejection without a channel."""
    s = Session()
    s.channel = None
    assert await confirm_tool(s, "write_file", {"path": "x", "content": "y"}) is False


# ─── 确认判定改由权限策略决定 ───


def _allow():
    from core.tools.policy import Decision
    return Decision("allow", "rule:test")


def _deny():
    from core.tools.policy import Decision
    return Decision("deny", "rule:test")


@pytest.mark.asyncio
async def test_confirm_allowed_tool_skips_asking(monkeypatch):
    """策略 allow 的工具直接放行，完全不提问。A policy-allowed tool passes without asking at all."""
    from core.orchestrator import confirm as confirm_mod
    monkeypatch.setattr(confirm_mod, "decide", lambda name, section=None: _allow())
    s = Session()
    s.channel = _Channel([])          # 没有可用答案 → 一旦提问就会 IndexError
    assert await confirm_tool(s, "run_shell_tool", {"command": "x"}) is True
    assert s.channel.notified == []   # 未发起任何询问


@pytest.mark.asyncio
async def test_confirm_denied_tool_refused_without_asking(monkeypatch):
    """策略 deny 的工具直接拒绝，不提问（问也没意义）。A policy-denied tool is refused without asking (asking would be pointless)."""
    from core.orchestrator import confirm as confirm_mod
    monkeypatch.setattr(confirm_mod, "decide", lambda name, section=None: _deny())
    s = Session()
    s.channel = _Channel([])
    assert await confirm_tool(s, "run_shell_tool", {"command": "x"}) is False
    assert s.channel.notified == []


@pytest.mark.asyncio
async def test_confirm_ask_tool_still_asks():
    """策略 ask 的工具照旧提问（回归：默认行为不变，多数工具都是 ask）。"""
    s = Session()
    s.channel = _Channel([Answer(choice="yes")])
    assert await confirm_tool(s, "write_file", {"path": "x", "content": "y"}) is True
    assert "需要确认" in s.channel.notified[0]


def test_confirm_options_labels_changed_but_values_unchanged():
    """弹窗文案改为「允许本次 / 拒绝」，但 value 保持 yes/no。

    因为不做 allow-always，文案需表达「这次而已」；value 不变使得
    _resolve_confirm 与全部既有回归用例不受影响。
    """
    from core.orchestrator.confirm import CONFIRM_OPTIONS
    assert CONFIRM_OPTIONS == [
        {"value": "yes", "label": "允许本次"},
        {"value": "no", "label": "拒绝"},
    ]
