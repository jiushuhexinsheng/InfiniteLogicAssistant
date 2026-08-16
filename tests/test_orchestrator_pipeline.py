# -*- coding: utf-8 -*-
import asyncio

import pytest

from core.orchestrator.pipeline import EventQueueChannel


@pytest.mark.asyncio
async def test_channel_ask_blocks_until_answer():
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")

    async def do_ask():
        return await ch.ask("问题?")

    t = asyncio.ensure_future(do_ask())
    await asyncio.sleep(0.05)
    # question 事件已入队（含 session_id，供前端回答）
    evt = await events.get()
    assert evt == {"type": "question", "question": "问题?", "session_id": "s1"}
    # 投递回答 → ask 返回
    ch.answer("回答")
    assert await t == "回答"


@pytest.mark.asyncio
async def test_channel_notify_puts_event():
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")
    await ch.notify("开始执行")
    assert await events.get() == {"type": "task_state", "state": "notify", "text": "开始执行", "session_id": "s1"}


@pytest.mark.asyncio
async def test_run_pipeline_seeds_messages(monkeypatch):
    from core.orchestrator.pipeline import run_pipeline
    from core.orchestrator.control import StopController
    from core.orchestrator.session import Session
    from core.orchestrator.intent import IntentResult

    async def fake_judge(text):
        return IntentResult(type="chit_chat", summary="打招呼")

    async def fake_stream(messages, **kw):
        # 断言多轮历史被带入：最后一个 user 消息是当前输入
        assert messages[-1]["role"] == "user" and messages[-1]["content"] == "你好"
        assert any(m["content"] == "昨天聊过" for m in messages)
        yield {"type": "content_delta", "text": "你好呀"}
        yield {"type": "done", "message": {"role": "assistant", "content": "你好呀"}}

    monkeypatch.setattr("core.orchestrator.pipeline.judge_intent", fake_judge)
    monkeypatch.setattr("core.orchestrator.pipeline.stream_chat", fake_stream)
    s = Session()
    events: asyncio.Queue = asyncio.Queue()
    await run_pipeline(
        "你好", s, events, StopController(),
        messages=[{"role": "user", "content": "昨天聊过"}],
    )
    assert s.messages[-1]["content"] == "你好"
    assert any(m["content"] == "昨天聊过" for m in s.messages)
    assert (await events.get())["type"] == "task_state"
    assert (await events.get())["type"] == "content_delta"
    assert (await events.get())["type"] == "done"
