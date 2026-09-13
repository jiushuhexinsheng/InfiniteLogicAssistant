# -*- coding: utf-8 -*-
"""任务形成（form_task）与澄清（run_clarify）的测试。
Tests for task formation (form_task) and clarification (run_clarify).
"""
import json

import pytest

from core.orchestrator.clarify import run_clarify
from core.orchestrator.intent import IntentResult
from core.orchestrator.session import Answer, Session
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
    """模拟 LLM 客户端，按脚本回放事件。Simulates an LLM client replaying scripted events."""

    def __init__(self, script):
        self.script = script

    def retry_stream_chat(self, messages, tools=None, **kwargs):
        async def gen():
            for evt in self.script.pop(0):
                yield evt
        return gen()


@pytest.mark.asyncio
async def test_form_task(monkeypatch):
    """从 LLM 的 form_task 调用形成任务。Forms a task from the LLM's form_task call."""
    fake = _FakeLLM([[_done_with_form("复制文件", {"src": "桌面readme.txt"}, ["复制到哪里？"], "write")]])
    monkeypatch.setattr("core.orchestrator.task.get_llm_client", lambda: fake)
    t = await form_task(IntentResult(type="task", summary="把桌面readme.txt复制到下载"))
    assert t.goal == "复制文件"
    assert t.params == {"src": "桌面readme.txt"}
    assert [m.question for m in t.missing] == ["复制到哪里？"]
    assert t.risk == "write"
    assert t.id


@pytest.mark.asyncio
async def test_run_clarify_asks_operator(monkeypatch):
    """澄清流程向操作者提问并返回补齐的参数。Clarification asks the operator and returns the completed params."""
    from core.orchestrator.task import MissingItem

    class _Channel:
        def __init__(self, answers):
            self.answers = list(answers)
            self.asked: list[str] = []
            self.kinds: list[str] = []

        async def ask(self, q, *, kind="text", options=None):
            self.asked.append(q)
            self.kinds.append(kind)
            a = self.answers.pop(0)
            return a if isinstance(a, Answer) else Answer(text=a)

        async def notify(self, text):
            pass

    script = [
        Task("t", "复制文件", {"src": "桌面readme.txt"}, [MissingItem(question="目标位置？")], "write"),
        Task("t", "复制文件", {"src": "桌面readme.txt", "dest": "下载"}, [], "write"),
    ]
    calls = {"n": 0}

    async def fake_form(intent, confirmed=None):
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
    assert s.channel.kinds == ["text"]
    assert params == {"src": "桌面readme.txt", "dest": "下载"}


@pytest.mark.asyncio
async def test_run_clarify_choice_answer_backfills_label(monkeypatch):
    """选择类缺失信息按 type 提问，回填 option 的 label（人类可读，供模型理解）。
    A choice-type missing item is asked as a choice question and backfills the option's
    label (human-readable, for the model to understand)."""
    from core.orchestrator.task import MissingItem

    class _Channel:
        def __init__(self):
            self.kinds: list[str] = []
            self.options: list[list] = []

        async def ask(self, q, *, kind="text", options=None):
            self.kinds.append(kind)
            self.options.append(options or [])
            return Answer(choice="dest-download")

        async def notify(self, text):
            pass

    script = [
        Task("t", "复制文件", {}, [MissingItem(
            question="复制到哪里？", type="choice",
            options=[{"value": "dest-download", "label": "下载目录"},
                     {"value": "dest-desktop", "label": "桌面"}],
        )], "write"),
        Task("t", "复制文件", {"dest": "下载目录"}, [], "write"),
    ]
    calls = {"n": 0}
    captured: dict = {}

    async def fake_form(intent, confirmed=None):
        captured["confirmed"] = confirmed
        t = script[min(calls["n"] + 1, len(script) - 1)]
        calls["n"] += 1
        return t

    monkeypatch.setattr("core.orchestrator.clarify.form_task", fake_form)

    s = Session()
    s.channel = _Channel()
    task = script[0]
    await run_clarify(s, task)
    # 以 choice 提问并带上选项
    assert s.channel.kinds == ["choice"]
    assert [o["value"] for o in s.channel.options[0]] == ["dest-download", "dest-desktop"]
    # 回填的是 label 而非 value
    assert captured["confirmed"] == {"复制到哪里？": "下载目录"}


@pytest.mark.asyncio
async def test_run_clarify_skips_already_asked_by_question(monkeypatch):
    """已问过的问题（按 question 文本判定）不再追问。Already-asked questions (matched by question text) are not asked again."""
    from core.orchestrator.task import MissingItem

    class _Channel:
        def __init__(self):
            self.asked: list[str] = []

        async def ask(self, q, *, kind="text", options=None):
            self.asked.append(q)
            return Answer(text="下载")

        async def notify(self, text):
            pass

    same = MissingItem(question="目标位置？")
    script = [
        Task("t", "复制文件", {}, [same], "write"),
        Task("t", "复制文件", {"dest": "下载"}, [same], "write"),
    ]
    calls = {"n": 0}

    async def fake_form(intent, confirmed=None):
        t = script[min(calls["n"] + 1, len(script) - 1)]
        calls["n"] += 1
        return t

    monkeypatch.setattr("core.orchestrator.clarify.form_task", fake_form)

    s = Session()
    s.channel = _Channel()
    await run_clarify(s, script[0])
    # 第二次循环看到同一个问题 → 停止追问，不重复提问
    assert s.channel.asked == ["目标位置？"]


# ─── parse_missing：LLM 输出不遵守 schema 时的三条容错 ───


def test_parse_missing_wraps_plain_strings():
    """模型不遵守 schema 时，字符串元素兜底为 text 类。Plain string items fall back to text when the model ignores the schema."""
    from core.orchestrator.task import parse_missing
    items = parse_missing(["目标位置？"])
    assert items[0].question == "目标位置？"
    assert items[0].type == "text"
    assert items[0].options == []


def test_parse_missing_defaults_unknown_type_to_text():
    """type 缺失或非法时降级为 text。A missing or invalid type degrades to text."""
    from core.orchestrator.task import parse_missing
    assert parse_missing([{"question": "a"}])[0].type == "text"
    assert parse_missing([{"question": "b", "type": "nonsense"}])[0].type == "text"


def test_parse_missing_downgrades_optionless_choice_to_text():
    """choice/composite 但没有选项时降级为 text —— 没有选项的选择题无法作答。
    A choice/composite without options degrades to text: an optionless multiple-choice is unanswerable."""
    from core.orchestrator.task import parse_missing
    for kind in ("choice", "composite"):
        assert parse_missing([{"question": "q", "type": kind, "options": []}])[0].type == "text"


def test_parse_missing_keeps_valid_choice():
    """合法的 choice（带选项）原样保留，选项只取 value/label。A valid choice keeps its options, keeping only value/label."""
    from core.orchestrator.task import parse_missing
    item = parse_missing([{
        "question": "选哪个？", "type": "choice",
        "options": [{"value": "a", "label": "甲", "extra": 1}],
    }])[0]
    assert item.type == "choice"
    assert item.options == [{"value": "a", "label": "甲"}]


def test_parse_missing_skips_empty_question():
    """空问题的条目不生成 MissingItem。Entries with an empty question produce no MissingItem."""
    from core.orchestrator.task import parse_missing
    assert parse_missing([{"question": "   "}, ""]) == []


@pytest.mark.asyncio
async def test_form_task_confirmed_keeps_goal_clean(monkeypatch):
    """confirmed 作为结构化信息单独传入 user 消息，goal/summary 不被污染。confirmed is passed to the user message separately as structured info so goal/summary stay clean."""
    captured = {}

    class _Capture:
        def retry_stream_chat(self, messages, tools=None, **kwargs):
            captured["messages"] = messages

            async def gen():
                yield _done_with_form(
                    "复制文件", {"src": "桌面readme.txt", "dest": "下载"}, [], "write",
                )
            return gen()

    monkeypatch.setattr("core.orchestrator.task.get_llm_client", lambda: _Capture())
    t = await form_task(
        IntentResult(type="task", summary="把桌面readme.txt复制到下载"),
        confirmed={"目标位置": "下载"},
    )
    user = captured["messages"][-1]["content"]
    assert "把桌面readme.txt复制到下载" in user  # goal 保持干净
    assert "已确认信息" in user                  # confirmed 单独呈现
    assert t.goal == "复制文件"
    assert t.params == {"src": "桌面readme.txt", "dest": "下载"}


@pytest.mark.asyncio
async def test_form_task_sets_created_timestamp(monkeypatch):
    """form_task 给任务打上创建时间戳（任务库存档需要）。
    form_task stamps the task with a creation timestamp (the task library needs it)."""
    fake = _FakeLLM([[_done_with_form("复制文件", {"src": "a"}, [], "write")]])
    monkeypatch.setattr("core.orchestrator.task.get_llm_client", lambda: fake)
    t = await form_task(IntentResult(type="task", summary="复制"))
    assert t.created, "created 不应为空"
    assert t.created[:2] == "20", f"应是 ISO 形如 20xx-...，实际 {t.created!r}"


def test_task_created_defaults_empty():
    """直接构造的 Task 时间戳缺省为空串（不破坏既有测试的构造方式）。
    A directly constructed Task defaults to an empty timestamp."""
    assert Task("t", "目标", risk="read").created == ""
