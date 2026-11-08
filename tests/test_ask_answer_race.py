# -*- coding: utf-8 -*-
"""预投递回答 / ask 竞态（docs/designs/10 5.2）。

两个缺陷：
1. `answer()` 不检查 `awaiting_answer` —— 问题出现前到达的回答会留在队列里，
   被下一个 ask() 当成它的回答吃掉；
2. `ask()` 先入队 question、后置 `awaiting_answer` —— 恰好落在窗口里的 stop/弃题
   看到「没有待答问题」，ask() 于是永远等下去（或等到超时）。

Pre-delivered answers / the ask race (docs/designs/10 5.2). Two defects:
1. `answer()` never checked `awaiting_answer`, so an answer arriving before the
   question stayed queued and was eaten by the next ask() as its own answer;
2. `ask()` enqueued the question before setting `awaiting_answer`, so a stop/abandon
   landing in that window saw "no pending question" and ask() waited forever.
"""
import asyncio

import pytest

from core.orchestrator.pipeline import EventQueueChannel


@pytest.mark.asyncio
async def test_answer_before_ask_is_rejected():
    """没有待答问题时投递回答 → 拒绝且不入队（不会喂给下一个问题）。"""
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, "sid")

    assert ch.answer("提前的回答", choice="yes") is False
    assert ch.answers.empty()
    assert events.empty()


@pytest.mark.asyncio
async def test_ask_sets_awaiting_before_question_event(monkeypatch):
    """question 事件入队时 awaiting_answer 必须已为真（stop 落在窗口内能看到待答）。"""
    from core import config as config_mod

    monkeypatch.setattr(config_mod.settings.agent, "confirm_timeout_s", 0.01)

    class FlagQueue(asyncio.Queue):
        def __init__(self) -> None:
            super().__init__()
            self.flag_at_put: bool | None = None

        async def put(self, item):
            self.flag_at_put = ch.awaiting_answer
            await super().put(item)

    events: FlagQueue = FlagQueue()
    ch = EventQueueChannel(events, "sid")

    ans = await ch.ask("确认执行吗？", kind="choice", options=[])

    assert events.flag_at_put is True
    # 超时路径正常收尾。The timeout path still cleans up.
    assert ans.choice == "no"
    assert ch.awaiting_answer is False


@pytest.mark.asyncio
async def test_abandon_inside_window_unblocks_ask(monkeypatch):
    """ask 刚开始（question 已发、调用方尚未 await 完）时弃题，ask 必须立刻返回。"""
    from core import config as config_mod
    from core.orchestrator.session import ABANDON_REASON

    monkeypatch.setattr(config_mod.settings.agent, "confirm_timeout_s", 0)

    class SlowPutQueue(asyncio.Queue):
        async def put(self, item):
            # 模拟「question 入队后、ask 挂起前」的调度点：此时 stop/弃题到达。
            await asyncio.sleep(0)
            await super().put(item)

    events: SlowPutQueue = SlowPutQueue()
    ch = EventQueueChannel(events, "sid")

    task = asyncio.create_task(ch.ask("确认执行吗？", kind="choice", options=[]))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert ch.abandon() is True
    ans = await asyncio.wait_for(task, timeout=1)
    assert ans.reason == ABANDON_REASON
