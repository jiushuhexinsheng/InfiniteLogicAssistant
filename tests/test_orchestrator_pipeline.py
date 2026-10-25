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
    # question 事件已入队（含 session_id / kind / options / qid，供前端决定渲染方式与问答配对）
    evt = await _next_event(events)
    assert evt["type"] == "question"
    assert evt["question"] == "问题?"
    assert evt["session_id"] == "s1"
    assert evt["kind"] == "text"
    assert evt["options"] == []
    assert evt["qid"].startswith("q_")
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
async def test_channel_answer_emits_answer_event():
    """投递回答时同步发射 AnswerEvent（作答入块、source 可审计）。
    Delivering an answer also emits an AnswerEvent (answers become blocks, source auditable)."""
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")

    async def do_ask():
        return await ch.ask("哪个城市？")

    t = asyncio.ensure_future(do_ask())
    qid = (await _next_event(events))["qid"]
    assert ch.answer("上海", source="voice") is True
    assert await asyncio.wait_for(t, timeout=1.0) == Answer(text="上海")
    answer_evt = await _next_event(events)
    assert answer_evt["type"] == "answer"
    assert answer_evt["qid"] == qid
    assert answer_evt["text"] == "上海"
    assert answer_evt["source"] == "voice"


@pytest.mark.asyncio
async def test_channel_answer_rejects_stale_qid():
    """qid 与待答问题不符 → 拒绝投递（防陈旧语音作答错配），answer 仍阻塞。
    A mismatched qid is refused (a stale voice answer cannot be mismatched); the
    ask() remains blocked."""
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")

    async def do_ask():
        return await ch.ask("哪个城市？")

    t = asyncio.ensure_future(do_ask())
    await _next_event(events)  # 消费 question 事件
    assert ch.answer("错误答案", qid="q_stale") is False
    # 未投递 → ask 仍阻塞；正确 qid 投递成功
    assert ch.answer("上海", qid=ch.pending_qid) is True
    assert await asyncio.wait_for(t, timeout=1.0) == Answer(text="上海")


@pytest.mark.asyncio
async def test_channel_answer_without_qid_is_legacy_passthrough():
    """不带 qid 的作答照旧投递（兼容旧前端/旧调用方）。
    An answer without qid is delivered as before (legacy callers unaffected)."""
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")

    async def do_ask():
        return await ch.ask("哪个城市？")

    t = asyncio.ensure_future(do_ask())
    await _next_event(events)
    assert ch.answer("上海") is True
    assert await asyncio.wait_for(t, timeout=1.0) == Answer(text="上海")


@pytest.mark.asyncio
async def test_channel_notify_puts_event():
    """notify 向事件队列写入通知事件。notify puts a notification event into the queue."""
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")
    await ch.notify("开始执行")
    assert await events.get() == {"type": "task_state", "state": "notify", "text": "开始执行", "session_id": "s1"}


@pytest.mark.asyncio
async def test_pipeline_runs_one_react_path_for_every_turn(monkeypatch):
    """不再区分闲聊/任务：所有输入都交给 execute_task 的执行循环。
    No chat/task split any more: every input goes through execute_task's loop."""
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.intent import IntentResult
    from core.orchestrator.session import Session

    seen_task = {}

    async def fake_judge(text):
        return IntentResult(summary="打个招呼")

    async def fake_execute(task, session, token, events, pause=None):
        seen_task.update(goal=task.goal, complexity=task.complexity)
        return {"status": "done", "summary": "你好呀", "steps": []}

    async def fake_extract(*a, **k):
        return None

    monkeypatch.setattr(pl, "judge_intent", fake_judge)
    monkeypatch.setattr(pl, "execute_task", fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", fake_extract)
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    s = Session()
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("你好", s, events, StopController())

    assert seen_task == {"goal": "你好", "complexity": "simple"}
    evts = _drain(events)
    assert evts[0]["type"] == "task_state" and evts[0]["state"] == "understanding"
    assert evts[-1]["type"] == "done"
    assert any(e.get("type") == "task_state" and e.get("state") == "done" for e in evts)


@pytest.mark.asyncio
async def test_run_pipeline_seeds_messages(monkeypatch):
    """管道把多轮历史与当前输入一起放进会话。The pipeline seeds multi-turn history plus the current input."""
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.intent import IntentResult
    from core.orchestrator.session import Session

    async def fake_judge(text):
        return IntentResult(summary="打招呼")

    async def fake_execute(task, session, token, events, pause=None):
        session.append("assistant", "你好呀")
        return {"status": "done", "summary": "你好呀", "steps": []}

    async def fake_extract(*a, **k):
        return None

    monkeypatch.setattr(pl, "judge_intent", fake_judge)
    monkeypatch.setattr(pl, "execute_task", fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", fake_extract)
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    s = Session()
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline(
        "你好", s, events, StopController(),
        messages=[{"role": "user", "content": "昨天聊过"}],
    )
    assert any(m["content"] == "你好" for m in s.messages)
    assert any(m["content"] == "昨天聊过" for m in s.messages)
    assert s.messages[-1]["role"] == "assistant"


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


@pytest.mark.asyncio
async def test_channel_abandon_resolves_pending_ask():
    """abandon() 解除阻塞的 ask：返回弃题毒丸（reason 标记），且不发 AnswerEvent
    —— 前端已自行清题，不该再冒出答案块。
    abandon() unblocks a pending ask() with a poison-pill Answer carrying the abandon
    reason, and emits no AnswerEvent (the frontend already cleared its card, so no
    answer block should appear)."""
    from core.orchestrator.session import ABANDON_REASON

    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")

    async def do_ask():
        return await ch.ask("确认执行吗？")

    t = asyncio.ensure_future(do_ask())
    await _next_event(events)  # question 事件已入队
    assert ch.abandon() is True
    ans = await asyncio.wait_for(t, timeout=1.0)
    assert ans == Answer(text="", choice=None, reason=ABANDON_REASON)
    assert events.empty(), "弃题不该发 AnswerEvent（前端已清题）"


@pytest.mark.asyncio
async def test_channel_abandon_without_pending_ask_is_noop():
    """不在等待回答时 abandon 是 no-op —— 毒丸绝不残留给下一个 ask。
    abandon() is a no-op when no ask is pending, so the poison pill can never leak
    into the next ask()."""
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")
    assert ch.abandon() is False

    # 队列无残留：下一个 ask 照常阻塞、靠真回答解除
    t = asyncio.ensure_future(ch.ask("问题?"))
    await _next_event(events)
    assert not t.done()
    ch.answer("回答")
    assert await asyncio.wait_for(t, timeout=1.0) == Answer(text="回答")


@pytest.mark.asyncio
async def test_ask_real_answer_wins_and_racing_poison_is_discarded():
    """真回答与弃题毒丸抢在同一轮（answer 先入队、abandon 后到）：ask 取真回答，
    毒丸必须被丢弃 —— 残留进下一个 ask 会让下一问开场即被取消。
    When a real answer lands before a racing abandon, ask() takes the real answer and
    the poison pill is discarded: a leaked pill would cancel the next question at birth."""
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")
    t = asyncio.ensure_future(ch.ask("第一问?"))
    await _next_event(events)
    ch.answer("真回答")
    # ask 尚未恢复运行（尚未 await），awaiting_answer 仍为 True → abandon 照常投毒
    assert ch.abandon() is True
    assert await asyncio.wait_for(t, timeout=1.0) == Answer(text="真回答")

    t2 = asyncio.ensure_future(ch.ask("第二问?"))
    await _next_event(events)
    assert not t2.done(), "弃题毒丸残留进了下一个 ask"
    ch.answer("第二答")
    assert await asyncio.wait_for(t2, timeout=1.0) == Answer(text="第二答")


# ─── 流水线测试助手 ───
# 流水线里 judge_intent / execute_task / extract_and_store 都是被 await 的，桩必须写成
# async def —— 用同步 lambda 会报 "object dict can't be used in 'await' expression"。
# These are all awaited by the pipeline, so the fakes must be async functions.

class _Channel:
    """预设答案的会话通道，并记录提问。A channel with preset answers that records questions."""

    def __init__(self, answers=None):
        self.answers = list(answers or [])
        self.asked: list[dict] = []

    async def ask(self, question, *, kind="text", options=None):
        self.asked.append({"question": question, "kind": kind, "options": options or []})
        return self.answers.pop(0)

    async def notify(self, text):
        pass


def _drain(q: asyncio.Queue) -> list:
    """排空队列。Drain the queue."""
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


async def _noop(*a, **k):
    """空协程。An empty coroutine."""
    return None


# ─── 反问：只在真的没把握时问一次 ───

@pytest.mark.asyncio
async def test_pipeline_asks_once_when_ambiguous_then_executes(monkeypatch):
    """没把握时只问一个问题（带选项），回答并入目标后继续执行。
    When unguessable: ask exactly one question (with options), fold the answer into the
    goal and carry on."""
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.intent import IntentResult
    from core.orchestrator.session import Answer, Session

    async def fake_judge(text):
        return IntentResult(summary="删除文件", ambiguous=True, question="要删除哪个文件？",
                            options=[{"value": "a.txt", "label": "a.txt"},
                                     {"value": "b.txt", "label": "b.txt"}])

    seen = {}

    async def fake_execute(task, session, token, events, pause=None):
        seen["goal"] = task.goal
        return {"status": "done", "summary": "已删除", "steps": []}

    monkeypatch.setattr(pl, "judge_intent", fake_judge)
    monkeypatch.setattr(pl, "execute_task", fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", _noop)
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    ch = _Channel([Answer(text="", choice="b.txt")])
    s = Session()
    s.channel = ch
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("把那个文件删了", s, events, StopController(), channel=ch)

    assert len(ch.asked) == 1
    assert ch.asked[0]["kind"] == "choice"
    assert ch.asked[0]["question"] == "要删除哪个文件？"
    assert "b.txt" in seen["goal"], "回答必须并入目标，否则模型等于没听见"
    assert "把那个文件删了" in seen["goal"]


@pytest.mark.asyncio
async def test_pipeline_abandoned_answer_cancels_without_executing(monkeypatch):
    """弃题（或空回答）不执行，直接以 cancelled 收束 —— 绝不用猜测继续。
    An abandoned (or empty) answer cancels the turn instead of executing on a guess."""
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.intent import IntentResult
    from core.orchestrator.session import ABANDON_REASON, Answer, Session

    async def fake_judge(text):
        return IntentResult(summary="删除文件", ambiguous=True, question="删哪个？")

    called = []

    async def fake_execute(*a, **k):
        called.append(True)
        return {"status": "done", "summary": "x", "steps": []}

    monkeypatch.setattr(pl, "judge_intent", fake_judge)
    monkeypatch.setattr(pl, "execute_task", fake_execute)

    ch = _Channel([Answer(text="", choice=None, reason=ABANDON_REASON)])
    s = Session()
    s.channel = ch
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("把那个文件删了", s, events, StopController(), channel=ch)

    assert called == [], "弃题后绝不能继续执行"
    evts = _drain(events)
    done_evt = next(e for e in evts if e.get("type") == "task_state" and e.get("state") == "done")
    assert done_evt["status"] == "cancelled"
    assert evts[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_pipeline_does_not_ask_when_confident(monkeypatch):
    """有把握时一次都不问（减少打断）。A confident turn asks nothing."""
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.intent import IntentResult
    from core.orchestrator.session import Session

    async def fake_judge(text):
        return IntentResult(summary="查天气")

    async def fake_execute(task, session, token, events, pause=None):
        return {"status": "done", "summary": "晴", "steps": []}

    monkeypatch.setattr(pl, "judge_intent", fake_judge)
    monkeypatch.setattr(pl, "execute_task", fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", _noop)
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    ch = _Channel([])
    s = Session()
    s.channel = ch
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("今天天气", s, events, StopController(), channel=ch)
    assert ch.asked == []


# ─── 复杂度 → 多智能体；mode 参数已失效 ───

@pytest.mark.asyncio
async def test_pipeline_passes_complexity_to_task(monkeypatch):
    """意图判出的复杂度随 Task 交给执行器（复杂才可能走多智能体）。
    The judged complexity rides along on the Task (only complex may go multi-agent)."""
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.intent import IntentResult
    from core.orchestrator.session import Session

    seen = {}

    async def fake_judge(text):
        return IntentResult(summary="大工程", complexity="complex")

    async def fake_execute(task, session, token, events, pause=None):
        seen["complexity"] = task.complexity
        return {"status": "done", "summary": "完成", "steps": []}

    monkeypatch.setattr(pl, "judge_intent", fake_judge)
    monkeypatch.setattr(pl, "execute_task", fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", _noop)
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    s = Session()
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("把整个项目梳理一遍", s, events, StopController())
    assert seen["complexity"] == "complex"


@pytest.mark.asyncio
async def test_pipeline_mode_is_accepted_but_ignored(monkeypatch):
    """旧前端的 mode="task" 不再触发完成追问或任务库存档（参数保留仅为兼容）。
    The legacy mode="task" no longer triggers a completion question or a library write
    (the parameter survives only for compatibility)."""
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import StopController
    from core.orchestrator.intent import IntentResult
    from core.orchestrator.session import Session

    async def fake_judge(text):
        return IntentResult(summary="做事")

    async def fake_execute(task, session, token, events, pause=None):
        return {"status": "done", "summary": "完成", "steps": []}

    monkeypatch.setattr(pl, "judge_intent", fake_judge)
    monkeypatch.setattr(pl, "execute_task", fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", _noop)
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    ch = _Channel([])
    s = Session()
    s.channel = ch
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("做事", s, events, StopController(), channel=ch, mode="task")
    assert ch.asked == [], "任务模式已删除，不应再追问「完成了吗」"


@pytest.mark.asyncio
async def test_pipeline_passes_pause_controller(monkeypatch):
    """暂停控制器要一路传到执行器（管线层不许半路丢掉）。
    The pause controller must reach the executor (the pipeline must not drop it)."""
    from core.orchestrator import pipeline as pl
    from core.orchestrator.control import PauseController, StopController
    from core.orchestrator.intent import IntentResult
    from core.orchestrator.session import Session

    async def fake_judge(text):
        return IntentResult(summary="做事")

    seen = {}

    async def fake_execute(task, session, token, events, pause=None):
        seen["pause"] = pause
        return {"status": "done", "summary": "完成", "steps": []}

    monkeypatch.setattr(pl, "judge_intent", fake_judge)
    monkeypatch.setattr(pl, "execute_task", fake_execute)
    monkeypatch.setattr(pl, "extract_and_store", _noop)
    monkeypatch.setattr(pl, "get_facts_store", lambda: object())

    pause = PauseController()
    s = Session()
    events: asyncio.Queue = asyncio.Queue()
    await pl.run_pipeline("做事", s, events, StopController(), pause=pause)
    assert seen["pause"] is pause


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

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_extract(task, result, store, session=None):
        started.set()
        await release.wait()

    async def fake_judge(text):
        return IntentResult(summary="测试任务")

    async def fake_execute(task, session, token, events, pause=None):
        return {"status": "done", "summary": "完成", "steps": []}

    monkeypatch.setattr(pl, "judge_intent", fake_judge)
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
