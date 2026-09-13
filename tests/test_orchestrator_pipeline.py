# -*- coding: utf-8 -*-
"""管道（EventQueueChannel / run_pipeline）的测试。
Tests for the pipeline (EventQueueChannel / run_pipeline).
"""
import asyncio

import pytest

from core.orchestrator.pipeline import EventQueueChannel
from core.orchestrator.session import Answer


class _FakeLLMClient:
    """模拟 LlmClient.retry_stream_chat；check 可选，用于断言收到的 messages。Simulates LlmClient.retry_stream_chat; check is optional for asserting the received messages."""

    def __init__(self, events=None, check=None):
        self.events = events or [
            {"type": "content_delta", "text": "你好呀"},
            {"type": "done", "message": {"role": "assistant", "content": "你好呀"}},
        ]
        self.check = check

    async def retry_stream_chat(self, messages, tools=None, *, profile=None, **kwargs):
        if self.check:
            self.check(messages)
        for e in self.events:
            yield e


async def _next_event(events: asyncio.Queue) -> dict:
    """取下一个事件，带超时 —— 事件未入队时快速失败而不是永久挂起。

    Take the next event with a timeout, so a missing event fails fast instead of hanging
    the whole suite (which is what happens when the producer raised before enqueuing).
    """
    return await asyncio.wait_for(events.get(), timeout=1.0)


@pytest.mark.asyncio
async def test_channel_ask_blocks_until_answer():
    """ask 阻塞直到收到回答；缺省 kind 为 text。ask blocks until an answer arrives; kind defaults to text."""
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")

    async def do_ask():
        return await ch.ask("问题?")

    t = asyncio.ensure_future(do_ask())
    # question 事件已入队（含 session_id / kind / options，供前端决定渲染方式）
    evt = await _next_event(events)
    assert evt == {"type": "question", "question": "问题?", "session_id": "s1", "kind": "text", "options": []}
    # 投递回答 → ask 返回
    ch.answer("回答")
    assert await asyncio.wait_for(t, timeout=1.0) == Answer(text="回答")


@pytest.mark.asyncio
async def test_channel_ask_choice_carries_options_and_choice():
    """选择类提问带 options，回答带结构化 choice。
    A choice question carries options, and the answer carries the structured choice."""
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")

    async def do_ask():
        return await ch.ask("确认执行吗？", kind="choice",
                            options=[{"value": "yes", "label": "确认"}, {"value": "no", "label": "取消"}])

    t = asyncio.ensure_future(do_ask())
    evt = await _next_event(events)
    assert evt["kind"] == "choice"
    assert evt["options"] == [{"value": "yes", "label": "确认"}, {"value": "no", "label": "取消"}]
    ch.answer("", choice="yes")
    assert await asyncio.wait_for(t, timeout=1.0) == Answer(text="", choice="yes")


@pytest.mark.asyncio
async def test_channel_ask_composite_kind():
    """综合类 kind 透传（前端渲染按钮 + 输入框）。A composite kind is passed through (frontend renders buttons plus an input)."""
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")

    async def do_ask():
        return await ch.ask("选一个并补充", kind="composite", options=[{"value": "a", "label": "甲"}])

    t = asyncio.ensure_future(do_ask())
    assert (await _next_event(events))["kind"] == "composite"
    ch.answer("补充说明")
    assert await asyncio.wait_for(t, timeout=1.0) == Answer(text="补充说明")


@pytest.mark.asyncio
async def test_channel_notify_puts_event():
    """notify 向事件队列写入通知事件。notify puts a notification event into the queue."""
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")
    await ch.notify("开始执行")
    assert await events.get() == {"type": "task_state", "state": "notify", "text": "开始执行", "session_id": "s1"}


@pytest.mark.asyncio
async def test_chit_chat_records_assistant_reply(monkeypatch):
    """闲聊回复记录进会话历史。Chit-chat replies are recorded into the session history."""
    from core.orchestrator.pipeline import run_pipeline
    from core.orchestrator.control import StopController
    from core.orchestrator.session import Session
    from core.orchestrator.intent import IntentResult

    async def fake_judge(text):
        return IntentResult(type="chit_chat", summary="打招呼")

    monkeypatch.setattr("core.orchestrator.pipeline.judge_intent", fake_judge)
    monkeypatch.setattr("core.orchestrator.pipeline.get_llm_client", lambda: _FakeLLMClient())
    s = Session()
    events: asyncio.Queue = asyncio.Queue()
    await run_pipeline("你好", s, events, StopController())
    # 闲聊回复应记录进会话历史（供完整历史保存）
    assert any(m.get("role") == "assistant" and "你好呀" in m.get("content", "") for m in s.messages)


@pytest.mark.asyncio
async def test_run_pipeline_seeds_messages(monkeypatch):
    """管道把多轮历史与当前输入一起喂给 LLM。The pipeline seeds the LLM with multi-turn history plus the current input."""
    from core.orchestrator.pipeline import run_pipeline
    from core.orchestrator.control import StopController
    from core.orchestrator.session import Session
    from core.orchestrator.intent import IntentResult

    async def fake_judge(text):
        return IntentResult(type="chit_chat", summary="打招呼")

    def check(messages):
        # 断言多轮历史被带入：最后一个 user 消息是当前输入
        assert messages[-1]["role"] == "user" and messages[-1]["content"] == "你好"
        assert any(m["content"] == "昨天聊过" for m in messages)

    monkeypatch.setattr("core.orchestrator.pipeline.judge_intent", fake_judge)
    monkeypatch.setattr("core.orchestrator.pipeline.get_llm_client", lambda: _FakeLLMClient(check=check))
    s = Session()
    events: asyncio.Queue = asyncio.Queue()
    await run_pipeline(
        "你好", s, events, StopController(),
        messages=[{"role": "user", "content": "昨天聊过"}],
    )
    assert any(m["content"] == "你好" for m in s.messages)
    assert any(m["content"] == "昨天聊过" for m in s.messages)
    # 闲聊回复记录进会话（供完整历史保存）
    assert s.messages[-1]["role"] == "assistant"
    assert (await events.get())["type"] == "task_state"
    assert (await events.get())["type"] == "content_delta"
    assert (await events.get())["type"] == "done"


@pytest.mark.asyncio
async def test_background_extract_task_is_referenced(monkeypatch):
    """后台记忆提取任务被持引用，且完成后自动移除（防 GC 导致静默丢失）。
    The background fact-extraction task is kept referenced and auto-discarded on
    completion (prevents silently losing it to GC).
    """
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.intent import IntentResult
    from core.orchestrator.session import Session
    from core.orchestrator.task import Task

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_extract(task, result, store):
        started.set()
        await release.wait()

    async def fake_judge(text):
        return IntentResult(type="task", summary="测试任务")

    async def fake_form_task(intent):
        return Task(id="t1", goal="测试", params={}, missing=[], risk="read")

    async def fake_execute(task, session, token, events):
        return {"status": "done", "summary": "完成", "steps": []}

    monkeypatch.setattr(pl, "judge_intent", fake_judge)
    monkeypatch.setattr(pl, "form_task", fake_form_task)
    monkeypatch.setattr(pl, "execute_task", fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", fake_extract)
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    pl._bg_tasks.clear()
    session = Session()
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("做事", session, events, StopController())
    await asyncio.wait_for(started.wait(), timeout=1)

    # 任务在飞行中被引用持有（旧实现无此集合 → AttributeError）
    assert len(pl._bg_tasks) == 1, "后台提取任务未被持引用，可能被 GC 回收"

    release.set()
    await asyncio.gather(*pl._bg_tasks)
    await asyncio.sleep(0)
    # 完成后 done_callback 已将其丢弃
    assert len(pl._bg_tasks) == 0, "已完成的后台任务未被清理，引用集会持续增长"


@pytest.mark.asyncio
async def test_channel_awaiting_answer_flag_tracks_ask():
    """ask() 期间 awaiting_answer 为 True，返回后复位 —— 供 /voice/utter 判断会话是否被占用。
    awaiting_answer is True while ask() is pending and resets afterwards, so /voice/utter
    can tell whether the session is busy."""
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")
    assert ch.awaiting_answer is False
    t = asyncio.ensure_future(ch.ask("问题?"))
    await asyncio.wait_for(events.get(), timeout=1.0)   # 事件入队即 ask 已进入阻塞
    assert ch.awaiting_answer is True
    ch.answer("回答")
    await asyncio.wait_for(t, timeout=1.0)
    assert ch.awaiting_answer is False


# ─── 流水线测试助手 ───
# 注意：流水线里 judge_intent / form_task / execute_task / run_clarify / extract_and_store
# 都是被 await 的，桩必须写成 async def —— 用同步 lambda 会报
# "object dict can't be used in 'await' expression"。
# These are all awaited by the pipeline, so the fakes must be async functions.

def _intent_task():
    """构造一个「任务」意图。Build a task intent."""
    from core.orchestrator.intent import IntentResult
    return IntentResult(type="task", summary="做事")


async def _fake_judge(text):
    """判定为任务意图。Classify as a task intent."""
    return _intent_task()


def _done_result():
    """构造一个成功结果。Build a successful result."""
    return {"status": "done", "summary": "完成", "steps": []}


async def _fake_execute(*a, **k):
    """返回成功结果。Return a successful result."""
    return _done_result()


async def _fake_clarify(sess, task):
    """澄清无额外产出。Clarification yields nothing."""
    return {}


async def _noop(*a, **k):
    """空协程。An empty coroutine."""
    return None


def _drain(q: asyncio.Queue) -> list:
    """排空队列。Drain the queue."""
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


# ─── 预填钩子（减少询问）───

@pytest.mark.asyncio
async def test_pipeline_prefills_params_from_similar_task(monkeypatch):
    """命中相似历史任务时，以历史参数作为 confirmed 重新 form_task（这样 missing 才会变小），
    并发出 notify 让用户看到。

    On a similar historical hit, form_task is re-run with the historical params as
    `confirmed` (only then does `missing` shrink) and a notify is emitted so the user sees it.
    """
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.session import Session
    from core.orchestrator.task import MissingItem, Task

    calls: list = []

    async def fake_form(intent, confirmed=None):
        calls.append(confirmed)
        if confirmed:
            return Task(id="t2", goal="复制文件", params=dict(confirmed), missing=[], risk="read")
        return Task(id="t1", goal="复制文件", params={},
                    missing=[MissingItem(question="目标位置？")], risk="read")

    async def fake_find(goal, **kw):
        return {"id": 1, "goal": goal, "params": {"dest": "下载"}, "created": "2026-09-13"}

    monkeypatch.setattr(pl, "form_task", fake_form)
    monkeypatch.setattr(pl, "find_similar", fake_find)
    monkeypatch.setattr(pl, "judge_intent", _fake_judge)
    monkeypatch.setattr(pl, "execute_task", _fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", _noop)
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    s = Session()
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("复制文件", s, events, StopController())

    assert calls == [None, {"dest": "下载"}], "第二次调用必须带 confirmed（历史参数）"
    assert s.task.params == {"dest": "下载"}
    notes = [e.get("text", "") for e in _drain(events) if e.get("type") == "task_state"]
    assert any("历史任务" in t for t in notes), "用户应能看到「参考了历史任务」"


@pytest.mark.asyncio
async def test_pipeline_skips_prefill_when_no_similar(monkeypatch):
    """无相似历史时不二次调用 form_task（避免无谓的 LLM 调用）。
    With no similar history, form_task is not called a second time."""
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.session import Session
    from core.orchestrator.task import MissingItem, Task

    calls: list = []

    async def fake_form(intent, confirmed=None):
        calls.append(confirmed)
        return Task(id="t1", goal="导出报表", params={},
                    missing=[MissingItem(question="哪个季度？")], risk="read")

    async def fake_find(goal, **kw):
        return None

    monkeypatch.setattr(pl, "form_task", fake_form)
    monkeypatch.setattr(pl, "find_similar", fake_find)
    monkeypatch.setattr(pl, "judge_intent", _fake_judge)
    monkeypatch.setattr(pl, "run_clarify", _fake_clarify)
    monkeypatch.setattr(pl, "execute_task", _fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", _noop)
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    s = Session()
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("导出报表", s, events, StopController())
    assert calls == [None], "无相似历史时不应二次调用 form_task"


# ─── 完成确认 + 存档（mode="task"）───

def _task_without_missing():
    """构造一个无缺失信息的任务。Build a task with nothing missing."""
    from core.orchestrator.task import Task
    return Task(id="t1", goal="做事", params={}, missing=[], risk="read")


async def _fake_form_plain(intent, confirmed=None):
    """不产生缺失信息的 form_task 桩（必须 async —— 流水线会 await 它）。
    A form_task stub that produces nothing missing (must be async; the pipeline awaits it)."""
    return _task_without_missing()


@pytest.mark.asyncio
async def test_task_mode_asks_completion_and_records_on_yes(monkeypatch):
    """任务模式下完成时发确认提问；答「完成了」才存档。
    In task mode a completion question is asked and the task is archived only on "completed"."""
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.session import Answer, Session

    recorded: list = []

    class _Ch:
        def __init__(self):
            self.kinds, self.options, self.notified = [], [], []
        async def ask(self, q, *, kind="text", options=None):
            self.kinds.append(kind)
            self.options.append(options or [])
            self.notified.append(q)
            return Answer(choice="yes")
        async def notify(self, text):
            self.notified.append(text)

    class _Store:
        async def record(self, task, result, session_id="", source_text=""):
            recorded.append((task.goal, session_id))

    monkeypatch.setattr(pl, "_get_task_store", lambda: _Store())
    monkeypatch.setattr(pl, "judge_intent", _fake_judge)
    monkeypatch.setattr(pl, "form_task", _fake_form_plain)
    monkeypatch.setattr(pl, "execute_task", _fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", _noop)
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    s = Session()
    ch = _Ch()
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("做事", s, events, StopController(), channel=ch, mode="task")

    assert ch.kinds == ["choice"], "完成确认必须是 choice 类"
    assert [o["value"] for o in ch.options[0]] == ["yes", "no"]
    assert recorded == [("做事", s.id)]


@pytest.mark.asyncio
async def test_task_mode_no_record_when_not_completed(monkeypatch):
    """答「没完成」不存档。Answering "not completed" does not archive."""
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.session import Answer, Session

    recorded: list = []

    class _Ch:
        async def ask(self, q, *, kind="text", options=None):
            return Answer(choice="no")
        async def notify(self, text):
            pass

    class _Store:
        async def record(self, task, result, session_id="", source_text=""):
            recorded.append(task.goal)

    monkeypatch.setattr(pl, "_get_task_store", lambda: _Store())
    monkeypatch.setattr(pl, "judge_intent", _fake_judge)
    monkeypatch.setattr(pl, "form_task", _fake_form_plain)
    monkeypatch.setattr(pl, "execute_task", _fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", _noop)
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    s = Session()
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("做事", s, events, StopController(), channel=_Ch(), mode="task")
    assert recorded == []


@pytest.mark.asyncio
async def test_chat_mode_never_asks_completion(monkeypatch):
    """对话模式（缺省）完全不问、不存档 —— 向后兼容回归。
    Chat mode (the default) never asks and never archives — a backward-compatibility regression."""
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.session import Answer, Session

    asked: list = []

    class _Ch:
        async def ask(self, q, *, kind="text", options=None):
            asked.append(q)
            return Answer(choice="yes")
        async def notify(self, text):
            pass

    monkeypatch.setattr(pl, "judge_intent", _fake_judge)
    monkeypatch.setattr(pl, "form_task", _fake_form_plain)
    monkeypatch.setattr(pl, "execute_task", _fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", _noop)
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    s = Session()
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("做事", s, events, StopController(), channel=_Ch())   # 缺省 mode
    assert asked == [], "对话模式不应发完成确认"
