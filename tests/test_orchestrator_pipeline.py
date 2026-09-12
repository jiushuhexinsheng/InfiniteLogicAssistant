# -*- coding: utf-8 -*-
"""管道（EventQueueChannel / run_pipeline）的测试。
Tests for the pipeline (EventQueueChannel / run_pipeline).
"""
import asyncio

import pytest

from core.orchestrator.pipeline import EventQueueChannel


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


@pytest.mark.asyncio
async def test_channel_ask_blocks_until_answer():
    """ask 阻塞直到收到回答。ask blocks until an answer arrives."""
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
