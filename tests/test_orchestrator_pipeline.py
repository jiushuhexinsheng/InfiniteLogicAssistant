# -*- coding: utf-8 -*-
import asyncio

import pytest

from core.orchestrator.pipeline import EventQueueChannel


@pytest.mark.asyncio
async def test_channel_ask_blocks_until_answer():
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events)

    async def do_ask():
        return await ch.ask("问题?")

    t = asyncio.ensure_future(do_ask())
    await asyncio.sleep(0.05)
    # question 事件已入队
    evt = await events.get()
    assert evt == {"type": "question", "question": "问题?"}
    # 投递回答 → ask 返回
    ch.answer("回答")
    assert await t == "回答"


@pytest.mark.asyncio
async def test_channel_notify_puts_event():
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events)
    await ch.notify("开始执行")
    assert await events.get() == {"type": "task_state", "state": "notify", "text": "开始执行"}
